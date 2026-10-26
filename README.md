# github-deep-search

**GitHub research eyes for AI agents** — deep project search + Trending, packaged as a single [Agent Skills](https://agentskills.io) folder.

English | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Standard: Agent Skills](https://img.shields.io/badge/standard-Agent%20Skills-green.svg)](https://agentskills.io)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org)
[![Dependencies: zero](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#security)

`gh search repos` returns a single ranked list. The official [GitHub MCP server](https://github.com/github/github-mcp-server) has no Trending tool at all. This skill targets the research-style question — *"find me open-source projects in this space"* — and adds:

- **Multi-strategy search** — merges best-match, stars and recency rankings, deduplicates, then re-ranks with a relevance score (log-compressed stars + activity bonus + keyword match − archive penalty). Full algorithm: [references/search-strategy.md](references/search-strategy.md)
- **CN ⇄ EN bilingual queries** — a Chinese keyword is automatically paired with its English translation and both result sets are merged, so you don't miss projects described only in English (or only in Chinese)
- **GitHub Trending** — daily / weekly / monthly, filterable by language, with an automatic RSS fallback when the page structure changes
- **Zero dependencies** — pure Python standard library; no pip install, no MCP setup, no API key required

## Requirements

**Required — only two things:**

- **Python 3.8+** — no pip packages, pure standard library
- Internet access to `api.github.com` and `github.com`. Behind a local proxy, note that **rule mode often skips terminal traffic** — if direct access fails, switch the proxy to global mode, set `HTTP_PROXY`/`HTTPS_PROXY`, or pass `--proxy http://127.0.0.1:7890` (the `--doctor` check reports the proxy it detects)

**One more thing, pick either:**

- An agent that supports the [Agent Skills](https://agentskills.io) standard (Claude Code, Codex, Cursor, Gemini CLI, …), **or** just a terminal — the scripts run standalone

**Optional — a GitHub token, for 3× rate limit** (30 vs 10 search requests/min), auto-detected from any one of:

- `gh` CLI logged in (`gh auth login`) — recommended, zero configuration
- `GITHUB_TOKEN` environment variable
- `--token` command-line flag

**Explicitly not needed:** MCP server setup, API key registration, third-party dependencies. Everything works anonymously out of the box.

## Install

Tell the AI agent you are using:

```text
Install this skill: https://github.com/Geerdan1995/github-deep-search
```

Agents that follow the Agent Skills standard (Claude Code, Codex, Cursor, Gemini CLI, …) will clone it into their own skills directory.

Manual install:

```bash
git clone https://github.com/Geerdan1995/github-deep-search.git
```

Then place it in your agent's skills directory (common locations — check your agent's docs if unsure):

| Agent | Skills directory |
|---|---|
| Claude Code | `~/.claude/skills/` (user-wide) or `.claude/skills/` (per project) |
| Codex | `~/.agents/skills/` |
| Cursor | `~/.cursor/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| GitHub Copilot | `~/.copilot/skills/` |
| Windsurf | `~/.codeium/windsurf/skills/` |

Post-install self-check (requires Python 3.8+):

```bash
python3 scripts/github_search.py --doctor
```

```
[✓] Python 3.13.14 (≥3.8)
[✓] Network: api.github.com reachable (675ms)
[✓] gh CLI logged in (Geerdan1995) → its token will be used automatically
[✓] Search API quota: 30/30 remaining (resets 22:11 UTC)
—— All good.
```

## Usage

### Deep search

```bash
python3 scripts/github_search.py "机器学习框架" --en "machine learning framework" --language python --limit 10
```

Example output (real run, trimmed):

| # | 项目 | 描述 | ⭐ Stars | 🍴 Forks | 语言 | 最近更新 |
|---|------|------|---------|---------|------|---------|
| 1 | [vitalets/github-trending-repos](https://github.com/vitalets/github-trending-repos) | Track GitHub trending repositories in your favorite programming language by nati… | 3.0k | 142 | HTML | 2026-10-11 |
| 2 | [bonfy/github-trending](https://github.com/bonfy/github-trending) | Tracking the most popular Github repos, update daily(Python version) | 1.2k | 236 | Python | 2026-10-25 |
| 3 | [mshibanami/GitHubTrendingRSS](https://github.com/mshibanami/GitHubTrendingRSS) | Unofficial RSS feed generator for GitHub Trending | 369 | 23 | HTML | 2026-10-25 |

Options: `--en` (English keywords to merge), `--language` (python/go/rust/…), `--limit` (default 15), `--json` (machine-readable), `--proxy <url>` (when a rule-mode proxy skips terminal traffic).

### Trending

```bash
python3 scripts/github_trending.py --since weekly --language python
```

Example output (real run, trimmed):

| # | 项目 | 描述 | ⭐ 总Star | 📈 本期增长 | 🍴 Forks | 语言 |
|---|------|------|---------|------------|---------|------|
| 1 | [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) | Open source repository of plugins primarily intended for knowledge wor… | 33.0k | +2.6k | 3.6k | Python |
| 2 | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | Turn any codebase, with its docs, SQL schemas, configs, and PDFs, into… | 135.2k | +6.9k | 12.9k | Python |

`--since`: `daily` / `weekly` (default) / `monthly`. If GitHub is unreachable or a page redesign breaks parsing, the script falls back to the [GitHubTrendingRSS](https://github.com/mshibanami/GitHubTrendingRSS) mirror and labels the data source in its output.

## Authentication (optional)

The token chain from [Requirements](#requirements) is resolved at startup and reported on stderr (`[i] Auth: gh CLI login`), so you always know which mode you are in. If you already use the [GitHub CLI](https://cli.github.com/), there is nothing to configure.

## Scope & limitations

- Repository search and Trending only — no issue/PR/code/user search (use `gh` or the official MCP server for those)
- The relevance score is a heuristic; stars/activity are compressed so niche-but-exact matches can outrank famous-but-vague ones
- Trending has no official API; the HTML parser carries multi-level fallbacks and an RSS mirror, but a major GitHub redesign may still need a parser update

## Security

- Zero third-party dependencies — pure Python standard library, easy to audit
- No telemetry; network requests go only to `api.github.com`, `github.com` and the RSS fallback host
- Your token stays on your machine and is sent only in request headers to `api.github.com`

## License

[MIT](LICENSE) — © 2026 万户AI造物 (Geerdan1995)
