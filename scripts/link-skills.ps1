# 通用技能挂载器：把 payload/skills 以 junction 挂进任意 AI 工具的技能根。
#
# 为什么用 junction（目录联接）：
#   一份真源、多工具共用；升级只改真源（junction 自动跟到新内容），撤销只删链接。
#   跨盘可用、Windows 上不需要管理员权限。
#
# 铁律：**每个工具只挂一个技能根。** 多数工具会同时扫多个根（Codex 扫 ~/.agents/skills
#   与 ~/.codex/skills；DSH 扫 ~/.dsh/skills、~/.agents/skills、~/.codex/skills），
#   同一个技能挂两处会让它出现两次。
#
# 用法:
#   pwsh -File scripts\link-skills.ps1                          # 挂 Codex 根（~/.agents/skills，默认 -Tool codex）
#   pwsh -File scripts\link-skills.ps1 -Tool codex,workbuddy    # 挂多个
#   pwsh -File scripts\link-skills.ps1 -Tool all                # 挂全部已知根
#   pwsh -File scripts\link-skills.ps1 -Tool workbuddy
#   pwsh -File scripts\link-skills.ps1 -Tool all -DryRun        # 只看现状
#   pwsh -File scripts\link-skills.ps1 -Tool all -Relink        # 先摘再挂
#   pwsh -File scripts\link-skills.ps1 -Tool all -Unlink        # 只摘本脚本挂过的
#   pwsh -File scripts\link-skills.ps1 -Root 'D:\some\skills'   # 任意自定义根
#
# 退出码：0=成功；1=硬错误；2=有跳过项（需要人看一眼）
#
# 踩过的坑（本机实测）：本脚本的开关参数曾叫 -Status，而内部有变量 $status 存状态字符串。
#   PowerShell 变量名大小写不敏感，赋值把开关覆盖成字符串，下一轮读它就报
#   「无法将 System.String 转换为 SwitchParameter」。→ 参数叫 -DryRun，内部变量叫 $state。

[CmdletBinding()]
param(
  [string[]]$Tool = @('codex'),
  [string[]]$Root = @(),
  [switch]$Relink,
  [switch]$Unlink,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$RepoRoot     = Split-Path -Parent $PSScriptRoot
$PayloadRoot  = Join-Path $RepoRoot 'payload\skills'
$ManifestPath = Join-Path $RepoRoot 'mounts.json'

# 已知工具根。key 供 -Tool 使用。
$KnownRoots = [ordered]@{
  'codex'     = "$env:USERPROFILE\.agents\skills"        # Codex CLI 与 DSH 都扫这个通用根
  'workbuddy' = "$env:USERPROFILE\.workbuddy\skills"     # WorkBuddy 用户级技能根
  'dsh'       = "$env:USERPROFILE\.dsh\skills"           # DSH 个人根（优先级高于上面的通用根）
  'claude'    = "$env:USERPROFILE\.claude\skills"
  'cursor'    = "$env:USERPROFILE\.cursor\skills"
  'codex-alt' = "$env:USERPROFILE\.codex\skills"         # 备选 Codex 根；与 codex 同时用会重复
}

if (-not (Test-Path $PayloadRoot)) { throw "找不到 payload 目录：$PayloadRoot" }

# ---- 解析目标根 ----
# 容错：`-Tool codex,workbuddy` 在 pwsh -File 调用下会被当成**一个**字符串传进来，
# 所以这里先把每个元素再按逗号拆一次（不这么做就得写成 -Tool codex workbuddy，容易踩）。
$Tool = @($Tool | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$targets = [ordered]@{}
if ($Tool -contains 'all') { $Tool = @($KnownRoots.Keys) }
foreach ($t in $Tool) {
  if (-not $KnownRoots.Contains($t)) {
    throw "未知工具 '$t'。已知：$($KnownRoots.Keys -join ', ')，或用 -Root 指定路径。"
  }
  $targets[$KnownRoots[$t]] = $t
}
foreach ($r in $Root) { $targets[[System.IO.Path]::GetFullPath($r)] = 'custom' }

# ---- 收集技能（一等公民判据：目录里有 SKILL.md）----
$skills = [ordered]@{}
foreach ($item in Get-ChildItem $PayloadRoot -Directory | Sort-Object Name) {
  $smd = Join-Path $item.FullName 'SKILL.md'
  if (-not (Test-Path $smd)) { Write-Warning "跳过 $($item.Name)：没有 SKILL.md"; continue }
  $head = Get-Content $smd -TotalCount 12 -Encoding UTF8
  if (-not ($head -match '^name:')) { Write-Warning "跳过 $($item.Name)：SKILL.md 缺 frontmatter name"; continue }
  if (-not ($head -match '^description:')) { Write-Warning "跳过 $($item.Name)：SKILL.md 缺 frontmatter description"; continue }
  $skills[$item.Name] = $item.FullName
}
if ($skills.Count -eq 0) { throw "payload 里没找到任何可用技能" }

# ---- 既有挂载记录（用于精确卸载）----
$allLinks = @()
if (Test-Path $ManifestPath) {
  try {
    $prev = Get-Content $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($prev.links) { $allLinks = @($prev.links) }
  } catch { Write-Warning "mounts.json 解析失败，忽略（不会误删任何东西）：$_" }
}

function Describe-State($link, $target) {
  $it = Get-Item $link -Force -ErrorAction SilentlyContinue
  if (-not $it) { return 'missing' }
  $isLink = $it.LinkType -in @('Junction', 'SymbolicLink')
  if ($isLink -and (@($it.Target) -contains $target)) { return 'ours' }
  if ($isLink) { return 'link-elsewhere' }
  return 'realdir'
}

# ---- 卸载：只摘"我们挂的、且指向本仓 payload"的链接 ----
if ($Unlink) {
  $removed, $kept = @(), @()
  foreach ($row in $allLinks) {
    if ($targets.Keys -notcontains $row.root) { $kept += $row; continue }
    $link = Join-Path $row.root $row.name
    if ((Describe-State $link $row.target) -eq 'ours') {
      if (-not $DryRun) { cmd /c rmdir "$link" | Out-Null }
      $removed += [pscustomobject]@{ root = $row.root; name = $row.name; state = if ($DryRun) { 'would-unlink' } else { 'unlinked' } }
    } else {
      $kept += $row
      $removed += [pscustomobject]@{ root = $row.root; name = $row.name; state = 'skipped-已不是我们的链接' }
    }
  }
  if (-not $DryRun) {
    [pscustomobject]@{ updatedAt = (Get-Date).ToString('o'); links = $kept } |
      ConvertTo-Json -Depth 4 | Set-Content $ManifestPath -Encoding UTF8
  }
  foreach ($r in $removed) { "{0,-20} {1,-32} {2}" -f (Split-Path $r.root -Leaf), $r.name, $r.state }
  exit 0
}

# ---- 挂载 / 现状检查 ----
$rows = @()
$skipped = 0
foreach ($rootPath in $targets.Keys) {
  if (-not (Test-Path $rootPath)) {
    if ($DryRun) {
      foreach ($name in $skills.Keys) {
        $rows += [pscustomobject]@{ root = $rootPath; name = $name; target = $skills[$name]; state = 'missing-root(未挂载)' }
      }
      continue
    }
    New-Item -ItemType Directory -Path $rootPath -Force | Out-Null
  }
  foreach ($name in $skills.Keys) {
    $link   = Join-Path $rootPath $name
    $target = $skills[$name]
    $st = Describe-State $link $target

    switch ($st) {
      'ours' {
        if ($Relink -and -not $DryRun) {
          cmd /c rmdir "$link" | Out-Null
          New-Item -ItemType Junction -Path $link -Target $target | Out-Null
          $state = 'relinked'
        } else { $state = 'ok-已挂载' }
      }
      'link-elsewhere' { $state = 'skipped-指向别处'; $skipped++ }
      'realdir'        { $state = 'skipped-实体目录已存在'; $skipped++ }
      default {
        if ($DryRun) { $state = 'missing-未挂载' }
        else {
          New-Item -ItemType Junction -Path $link -Target $target | Out-Null
          $state = 'linked'
        }
      }
    }
    $rows += [pscustomobject]@{ root = $rootPath; name = $name; target = $target; state = $state }
  }
}

# ---- 写清单：合并本次涉及的根，保留其它根的旧记录 ----
if (-not $DryRun) {
  $kept = @($allLinks | Where-Object { $targets.Keys -notcontains $_.root })
  [pscustomobject]@{
    updatedAt = (Get-Date).ToString('o')
    payload   = $PayloadRoot
    links     = @($kept) + @($rows | Where-Object { $_.state -notlike 'missing*' })
  } | ConvertTo-Json -Depth 4 | Set-Content $ManifestPath -Encoding UTF8
}

# ---- 汇报 ----
foreach ($g in $rows | Group-Object root) {
  "== $($g.Name)  [$($targets[$g.Name])]"
  foreach ($r in $g.Group) { "   {0,-20} {1}" -f $r.name, $r.state }
}
if ($skipped -gt 0) {
  ""
  "注意：$skipped 项被跳过（同名实体目录或指向别处的链接，本脚本一律不碰）。"
  "要强制接管，先确认那个目录不是别处正在用的东西，再手工 rmdir 后重跑。"
  exit 2
}
exit 0
