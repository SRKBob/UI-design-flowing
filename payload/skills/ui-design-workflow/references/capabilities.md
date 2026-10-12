# 工具能力矩阵与降级路径

本工作流的设计目标是「同一套流程在 Codex、WorkBuddy、DSH、Claude Code、Cursor 等工具里都能跑」。差异只集中在三处，其余全部是纯文本约定，天然通用。

## 1. 技能发现位置

| 工具 | 用户级技能根 | 项目级技能根 | 调用方式 |
|---|---|---|---|
| **Codex CLI** | `~/.agents/skills/`、`~/.codex/skills/` | `<项目>/.agents/skills/` | `/skills` 列表，或输入 `$技能名`，或自然语言触发 |
| **WorkBuddy** | `~/.workbuddy/skills/` | 同类约定 | 自动按 `description` 触发；用户级技能任意项目可见 |
| **DeepSeek Harness** | `~/.dsh/skills/`、`~/.agents/skills/`、`~/.codex/skills/` | `<项目>/.dsh/skills/`、`<项目>/.agents/skills/` | 工具 `skill`，或自然语言触发 |
| **Claude Code** | `~/.claude/skills/` | `<项目>/.claude/skills/` | `/技能名` |
| **Cursor** | `~/.cursor/skills/` | `<项目>/.cursor/skills/` | 自然语言触发（需在设置里启用 Agent Skills） |

`~/.agents/skills/` 是跨工具的公约数位置：Codex、DSH 都扫它。**优先挂这里**，需要时再用目录链接（junction / symlink）镜像到各工具自己的根。

## 2. 前端技能需要的运行时能力

| 能力 | 谁需要 | Codex | WorkBuddy | DSH | 都没有时的降级 |
|---|---|---|---|---|---|
| **浏览器截图 / 取 DOM** | `taste`（提取参照站设计 DNA）；④ 的视觉核查 | 内置浏览器工具或 Playwright MCP | 内置浏览器能力 | `browser_*` 工具 | 让用户手贴截图或该站的设计变量；或改用「只看代码不看渲染」的审查，并在报告里注明未做视觉核查 |
| **Python 3** | `ui-ux-pro-max` 的查表脚本 | 本机 `python`（注意 Windows 上 `python3` 可能是微软商店的桩） | 视安装环境 | 已具备 | 不跑脚本，直接读它 `data/` 下的 CSV/JSON 数据表，按同样维度人工选型（慢但可行） |
| **子 agent 并行** | 无。本工作流四段是串行的 | 有 | 视版本 | 有（`subagent` / `workflow`） | 直接顺序执行，不降质，只变慢 |
| **官方斜杠命令** | 无 | `$技能名` | 自然语言 | 自然语言 / `skill` 工具 | 一律用自然语言描述要做什么 |

**结论**：唯一的硬依赖是 `ui-ux-pro-max` 的 Python 脚本。没有 Python 时按上表降级——它的核心价值是 `data/` 里的数据表，脚本只是检索层。

## 3. 产物落盘约定

与工具无关，全是普通 Markdown / JSON 文件，任何工具都能读写。**约定见 `design-truth.md`**——这是整套工作流唯一的「真相来源」，多份约定并存会互相打架。

## 4. 挂载方式的选择

| 方式 | 优点 | 代价 |
|---|---|---|
| **目录链接（junction / symlink）指向一份真源** | 一份真源、升级一次全生效、撤销=删链接 | 需要文件系统支持链接；Windows 上 `New-Item -ItemType Junction` 不需管理员 |
| **复制实体目录** | 兼容性最好、目标工具零要求 | 多份副本会漂移；升级要逐份覆盖 |

本仓库的推荐：**真源在本仓库的 `payload/skills/`，用 `scripts/link-codex.ps1` 以 junction 挂到技能根**。若某工具确实不认链接（先实测，别假设），对那个工具单独改复制模式。
