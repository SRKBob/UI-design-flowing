# UI-design-flowing

一套**可移植的 UI 设计工作流**：一份 git 真源，挂给不同 AI 工具（Codex / DSH / WorkBuddy…）共用。

核心主张来自抖音博主「西瓜同学」那期视频（[原视频](https://v.douyin.com/soWFnXHf_M4/)）：**不是让 AI 更努力，是让它在正确的时间做正确的事。**

```
① 需求分析 SPEC  →  ② 前置 Skill ROUTE  →  ③ 生成页面 BUILD  →  ④ 代码理解 GRAPH
   把话变成规范        这一页按谁的规矩        到这才开始写代码        关系图建起来
```

四个角色在同一个项目里**接力**，不是四件互不相干的事。中间真正写代码的那一段，只需要专心写代码。

## 仓里有什么

```
UI-design-flowing/
├── payload/skills/          ← 技能真源（入 git）。各 AI 工具直接加载这一份
│   ├── ui-design-workflow/      编排层：四段式流程、SPEC 模板、路由矩阵、工具差异（本仓原创）
│   ├── ui-ux-pro-max/           ② 定方向：按产品类型查表出设计系统（51 文件）
│   ├── taste/                   ② 可选：给个 URL 反推该站的设计 DNA
│   ├── interface-design/        ② 可选：既有产品视觉体系的方向与跨会话一致性
│   └── impeccable/              ③ 的上限 + ④ 的交付检查与去 AI 味（64 文件）
├── snapshots/               ← 精简上游源码（入 git）。供**离线**重抽 payload，5.6MB
├── scripts/
│   ├── sync-upstream.py         三层同步：build / extract / check / fetch / update / validate
│   └── link-skills.ps1          把 payload 以 junction 挂进任意工具的技能根
├── upstream.json            pin 记录 + 每个技能的抽取路径 + 决策日志
├── NOW.md                   给非工程读者看的大白话说明
└── vendor/                  完整上游浅克隆（不入 git，仅升级上游时用，可丢弃重建）
```

**三层为什么这么分**：`snapshots` 是能离线复现的最小子集（已剔除 `.git`、文档站、测试、图片素材）；`payload` 是工具真正加载的技能目录；`vendor` 是完整上游，体积大且会随上游漂，只在升级时出现。日常升级只需 `extract`（离线），拉新版本才用 `update`（联网）。

## 挂载

```powershell
pwsh -File scripts\link-skills.ps1                          # 默认挂 Codex 根（~/.agents/skills）
pwsh -File scripts\link-skills.ps1 -Tool codex,workbuddy    # 挂多个
pwsh -File scripts\link-skills.ps1 -Tool all                # 挂全部已知根
pwsh -File scripts\link-skills.ps1 -Tool all -DryRun        # 只看现状，不改动
pwsh -File scripts\link-skills.ps1 -Tool all -Unlink        # 只摘本脚本挂过的（不动别人的目录）
pwsh -File scripts\link-skills.ps1 -Root 'D:\some\skills'   # 任意自定义根
```

| `-Tool` 取值 | 路径 | 说明 |
|---|---|---|
| `codex`（默认） | `~/.agents/skills` | Codex CLI 与 DSH 都扫这个通用根 |
| `workbuddy` | `~/.workbuddy/skills` | WorkBuddy 用户级技能根 |
| `dsh` | `~/.dsh/skills` | DSH 个人根（优先级更高） |
| `claude` / `cursor` | `~/.claude/skills`、`~/.cursor/skills` | |
| `codex-alt` | `~/.codex/skills` | 备选；**与 `codex` 同时挂会重复** |

**铁律：每个工具只挂一个技能根。** 多数工具会同时扫多个根，同一技能挂两处就会在列表里出现两次。

## 各工具的验证状态

| 工具 | 目录就位 | 工具能识别 | 怎么验的 |
|---|---|---|---|
| Codex CLI 0.160.1 | ✅ 5/5 | ✅ **实测** | `codex exec` 问答：5 个技能全部列出，且能透过 junction 读出真源引用文件 |
| DSH | ✅ 5/5 | ✅ **实测** | 技能目录刷新出现 5 个（与 Codex 共用 `~/.agents/skills`） |
| WorkBuddy | ✅ 5/5 | ⏳ **未验证** | 本机没装 WorkBuddy（无 exe、无进程），无法实测 |

装好 WorkBuddy 后按序验三步：①看它的技能列表有没有 `ui-design-workflow`，不认就是把 junction 改复制模式；②若它要求 `agent_created: true`，给 `payload/skills/*/SKILL.md` 的 frontmatter 各加一行（对 Codex 无害）；③对照 `~/.workbuddy/.skill-list-cache.json` 有没有新增这 5 条。

## 维护

```powershell
python scripts\sync-upstream.py check      # 三层现状：快照 / payload / vendor
python scripts\sync-upstream.py extract    # 离线：从 snapshots 重抽 payload（日常用这个）
python scripts\sync-upstream.py build      # 离线：从 vendor 重新生成 snapshots
python scripts\sync-upstream.py fetch      # 联网只读：查上游有没有新版
python scripts\sync-upstream.py update     # 联网：拉上游 → 刷新 snapshots + payload
python scripts\sync-upstream.py validate   # 校验 payload 结构与 frontmatter
```

挂载用 junction，**升级后不用重建链接**——`payload` 内容换掉，链接自然跟到新内容；只有技能**增删**时才要重跑挂载。

## 每个技能来自哪

| 技能 | 上游 | 许可证 | pin |
|---|---|---|---|
| ui-ux-pro-max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | MIT | tag `v2.15.0` (`a38d04c`) |
| taste | [senlindesign/taste-skill](https://github.com/senlindesign/taste-skill) | MIT（上游未提交 LICENSE 文件） | commit `6dce223` |
| interface-design | [Dammyjay93/interface-design](https://github.com/Dammyjay93/interface-design) | MIT | commit `2f9be32` |
| impeccable | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | Apache-2.0 | commit `c63b8dd`（引擎 0.1.14） |

`ui-design-workflow` 是本仓原创，不属于任何上游。

## 已知冲突与注意

1. **`impeccable` 可能有两个版本**：若本机早有 `~/.codex/skills/impeccable`（旧引擎 0.1.12），它与本仓 0.1.14 同名、description 一样，只能靠路径区分（在 Codex 里跑 `/skills` 看）。挂载脚本**刻意不接管**已存在的同名目录。
2. **`ui-ux-pro-max` 的查表脚本要 Python 3**。Windows 上用 `python`，不要用 `python3`（后者常是微软商店的占位程序）。没有 Python 时按 `payload/skills/ui-design-workflow/references/capabilities.md` 的降级路径走：直接读 `data/` 里的 CSV/JSON。
3. **`taste` 原生依赖 Playwright MCP + Chromium**（首次约 100MB）。本仓不硬绑：能力矩阵里给了"改用各工具自带浏览器工具"和"让用户贴截图"两条降级路。
4. **设计产物只有一套归属**（`SPEC.md` → `design-system/<slug>/pages/*.md` → `MASTER.md` → `.interface-design/system.md`），仲裁顺序写在编排 skill 的正文里。三套约定并存而不分主次，必然互相打架。
5. **`interface-design` 不管落地页**。它自己声明只适用于 dashboard / admin / SaaS / 工具类产品界面。
6. `vendor/`、`mounts.json`、`sync-report.txt` 都不入 git；`_video/`（本地抽帧产物）也不入 git。
