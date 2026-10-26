# github-deep-search

**给 AI Agent 的 GitHub 调研眼睛** —— 深度搜索开源项目 ＋ Trending 热榜，打包成一个 [Agent Skills](https://agentskills.io) 标准文件夹。

[English](README.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Standard: Agent Skills](https://img.shields.io/badge/standard-Agent%20Skills-green.svg)](https://agentskills.io)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org)
[![Dependencies: zero](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#安全与隐私)

`gh search repos` 只给你一份排序结果；官方 [GitHub MCP server](https://github.com/github/github-mcp-server) 连 Trending 工具都没有。这个 skill 面向的是调研型问题——"帮我找这个领域的开源项目"——补上：

- **多策略搜索** —— best-match / stars / 更新时间三种排序合并去重，再按相关性重排（对数压缩 star ＋ 活跃度加权 ＋ 关键词命中 − 归档惩罚）。完整算法：[references/search-strategy.md](references/search-strategy.md)
- **中英双语查询** —— 中文关键词自动配对英文翻译，两份结果合并，不会漏掉只用英文（或只用中文）描述的项目
- **GitHub Trending** —— 今日/本周/本月 × 编程语言筛选；页面结构变更时自动降级 RSS 后备源
- **零依赖** —— 纯 Python 标准库；不用 pip install、不用配 MCP、不用 API key（有更佳）

## 使用前提

**必须有——只有两样：**

- **Python 3.8+** —— 不用装任何 pip 包，纯标准库
- 能访问 `api.github.com` 和 `github.com` 的网络。本机开代理时注意**规则模式经常不代理终端流量**——直连失败就切全局模式、设 `HTTP_PROXY`/`HTTPS_PROXY`，或加 `--proxy http://127.0.0.1:7890`（`--doctor` 自检会显示当前检测到的代理）

**再加一样，二选一：**

- 一个支持 [Agent Skills](https://agentskills.io) 标准的 agent（Claude Code、Codex、Cursor、Gemini CLI 等），**或者**直接用终端——脚本可以独立运行

**可选——GitHub token，提速 3 倍**（搜索 30 次/分 vs 匿名 10 次/分），三选一自动探测：

- 已登录的 `gh` CLI（`gh auth login`）——推荐，零配置
- `GITHUB_TOKEN` 环境变量
- `--token` 命令行参数

**明确不需要：**MCP 服务配置、API key 申请、第三方依赖。开箱即可匿名使用。

## 安装

对你正在用的 AI agent 说：

```text
帮我安装这个 skill：https://github.com/Geerdan1995/github-deep-search
```

支持 Agent Skills 标准的 agent（Claude Code、Codex、Cursor、Gemini CLI 等）会自己把它装进 skills 目录。

手动安装：

```bash
git clone https://github.com/Geerdan1995/github-deep-search.git
```

然后放进你的 agent 的 skills 目录（常见位置，拿不准查各 agent 文档）：

| Agent | skills 目录 |
|---|---|
| Claude Code | `~/.claude/skills/`（用户级）或 `.claude/skills/`（项目级） |
| Codex | `~/.agents/skills/` |
| Cursor | `~/.cursor/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| GitHub Copilot | `~/.copilot/skills/` |
| Windsurf | `~/.codeium/windsurf/skills/` |

装完自检（需 Python 3.8+）：

```bash
python3 scripts/github_search.py --doctor
```

```
[✓] Python 3.13.14 (≥3.8)
[✓] 网络可达 api.github.com (675ms)
[✓] gh CLI 已登录 (Geerdan1995) → 将自动使用其 token
[✓] Search API 限额: 30/30 剩余（重置于 22:11 UTC）
—— 一切就绪。
```

## 用法

### 深度搜索

```bash
python3 scripts/github_search.py "机器学习框架" --en "machine learning framework" --language python --limit 10
```

示例输出（真实运行结果，截取）：

| # | 项目 | 描述 | ⭐ Stars | 🍴 Forks | 语言 | 最近更新 |
|---|------|------|---------|---------|------|---------|
| 1 | [vitalets/github-trending-repos](https://github.com/vitalets/github-trending-repos) | Track GitHub trending repositories in your favorite programming language by nati… | 3.0k | 142 | HTML | 2026-10-11 |
| 2 | [bonfy/github-trending](https://github.com/bonfy/github-trending) | Tracking the most popular Github repos, update daily(Python version) | 1.2k | 236 | Python | 2026-10-25 |
| 3 | [mshibanami/GitHubTrendingRSS](https://github.com/mshibanami/GitHubTrendingRSS) | Unofficial RSS feed generator for GitHub Trending | 369 | 23 | HTML | 2026-10-25 |

参数：`--en`（合并搜索的英文关键词）、`--language`（python/go/rust/…）、`--limit`（默认 15）、`--json`（程序化处理）、`--proxy <url>`（规则模式代理不覆盖终端时用）。

### Trending 热榜

```bash
python3 scripts/github_trending.py --since weekly --language python
```

示例输出（真实运行结果，截取）：

| # | 项目 | 描述 | ⭐ 总Star | 📈 本期增长 | 🍴 Forks | 语言 |
|---|------|------|---------|------------|---------|------|
| 1 | [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) | Open source repository of plugins primarily intended for knowledge wor… | 33.0k | +2.6k | 3.6k | Python |
| 2 | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | Turn any codebase, with its docs, SQL schemas, configs, and PDFs, into… | 135.2k | +6.9k | 12.9k | Python |

`--since`：`daily`（今日）/ `weekly`（本周，默认）/ `monthly`（本月）。GitHub 不可达或改版导致解析失败时，自动降级 [GitHubTrendingRSS](https://github.com/mshibanami/GitHubTrendingRSS) 后备源，并在输出中标注实际数据源。

## 认证（可选）

[使用前提](#使用前提)里的 token 探测链在启动时解析并打到 stderr（`[i] 认证: gh CLI 登录态`），当前处于哪种模式一目了然。已经在用 [GitHub CLI](https://cli.github.com/) 的话，什么都不用配。

## 边界与局限

- 只搜仓库和热榜——不搜 issue/PR/代码/用户（那些用 `gh` 或官方 MCP）
- 相关性评分是启发式；star/活跃度做了对数压缩，精准匹配的小项目能排赢"有名但跑题"的大项目
- Trending 没有官方 API；HTML 解析器带多重兜底＋RSS 镜像后备，但 GitHub 大改版仍可能需要更新解析器

## 安全与隐私

- 零第三方依赖——纯 Python 标准库，可整仓审计
- 无遥测；网络请求只发往 `api.github.com`、`github.com` 和 RSS 后备源
- token 只留在本机，仅用于向 `api.github.com` 发请求时的请求头

## License

[MIT](LICENSE) —— © 2026 万户AI造物 (Geerdan1995)
