---
name: github-deep-search
description: >-
  深度搜索 GitHub 开源项目 + GitHub Trending 热榜查询。中英文双语搜索，
  中文无结果自动转英文重试，多策略合并去重打分，结构化输出项目名/描述/star数/fork数/最近更新/链接。
  触发词：搜索github、github搜索、找开源项目、搜github仓库、github trending、github热榜、
  本周热榜、本月热榜、今日热榜、热门开源项目、github流行项目、搜开源、找库、找框架。
  不含：普通网页搜索、非GitHub代码搜索、GitHub issue/PR搜索、GitHub用户搜索。
license: MIT
compatibility: Requires Python 3.8+ (stdlib only, zero dependencies) and internet access. Optional: GITHUB_TOKEN env or gh CLI login for higher API rate limits.
metadata:
  version: "1.1.0"
  author: "万户AI造物 (Geerdan1995)"
---

# GitHub Deep Search

深度搜索 GitHub 开源项目 + Trending 热榜查询。两个核心能力：

1. **深度搜索** — 多策略合并（best-match × stars × updated 三种排序）、中英文双语自动合并去重、按相关性打分排序
2. **Trending 热榜** — 抓取 github.com/trending，按时间范围和编程语言筛选

## 能力边界

**owns（本 skill 负责）**：
- GitHub 仓库深度搜索（按关键词找开源项目/库/框架）
- GitHub Trending 热榜查询（今日/本周/本月 × 编程语言）

**不路由到这里（near-neighbor 排除）**：
- 普通 web 搜索（用 WebSearch）
- 非 GitHub 的代码搜索
- GitHub issue/PR/code search（本 skill 只搜仓库和热榜）
- GitHub 用户/组织搜索

## 环境要求

仅需 Python 3.8+，零第三方依赖。命令中的 `scripts/` 为本 skill 目录下的相对路径。macOS/Linux 用 `python3`；Windows 下若无 `python3` 命令，用 `python` 或 `py` 代替。

## 工作流

### 路径 A：深度搜索项目

用户想找某个领域的开源项目时：

1. **提取关键词**：从用户请求中提取搜索关键词
2. **双语处理**：如果关键词是中文，同时准备英文翻译关键词（你自行翻译，力求准确）
3. **运行脚本**：

```bash
python3 scripts/github_search.py "中文关键词" --en "english keywords" --language python --limit 15
```

参数说明：
- `--en`：英文关键词（中文查询时强烈建议提供，合并搜索覆盖更广）
- `--language`：编程语言筛选（可选，如 python/go/rust/javascript）
- `--limit`：返回数量（默认 15）
- `--json`：JSON 输出（需要程序化处理时用）
- `--proxy`：HTTP 代理（如 `http://127.0.0.1:7890`），网络不通时用，见路径 C 处置流程

4. **解读结果**：将 Markdown 表格呈现给用户，补充你的专业解读（哪些项目适合什么场景）

### 路径 B：Trending 热榜

用户问"本周热榜""热门项目""github trending"时：

```bash
python3 scripts/github_trending.py --since weekly --language python
```

参数说明：
- `--since`：`daily`（今日）/ `weekly`（本周）/ `monthly`（本月），默认 weekly
- `--language`：编程语言筛选（可选）
- `--json`：JSON 输出

用户说"本周热榜"→ `--since weekly`；"本月"→ `--since monthly`；"今天/今日"→ `--since daily`。

### 路径 C：安装自检（排障时用）

用户报告 skill 不工作、或刚安装完要验证环境时：

```bash
python3 scripts/github_search.py --doctor
```

输出四项检查：Python 版本 / api.github.com 连通性 / 认证来源（token 或 gh CLI 登录态）/ Search API 限额余量。全部 `[✓]` 即环境就绪。

**网络不通时的处置（重要）**：doctor 或搜索报 `无法连接 api.github.com` / 网络错误时，**先与用户确认本地代理情况，不要反复裸重试**：

1. 问用户：本机是否开着代理（Clash/v2ray 等）？是规则模式还是全局模式？代理端口是多少（常见 7890 / 10809 / 1080）？
2. 按用户回答处置——不是所有代理都开全局模式，规则模式经常不代理终端流量：
   - 知道端口：用 `--proxy http://127.0.0.1:端口` 重跑（或设 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量）
   - 不清楚端口：请用户在代理客户端查看，或临时切全局模式后重跑
3. 重跑 doctor 验证连通：`python3 scripts/github_search.py --doctor --proxy http://127.0.0.1:端口`，输出里会显示当前检测到的代理（`[i] 代理: …`）

## 输出格式

两个脚本默认输出 Markdown 表格，直接呈现给用户即可。

**搜索结果表格**：

| # | 项目 | 描述 | ⭐ Stars | 🍴 Forks | 语言 | 最近更新 |
|---|------|------|---------|---------|------|---------|

**热榜表格**：

| # | 项目 | 描述 | ⭐ 总Star | 📈 本期增长 | 🍴 Forks | 语言 |
|---|------|------|---------|------------|---------|------|

项目名为可点击的 Markdown 链接，用户可直接访问。

## 重要说明

- **认证自动探测**：脚本按 `--token` 参数 > `GITHUB_TOKEN` 环境变量 > `gh CLI 登录态` > 匿名 的顺序自动取 token。本机装有 gh CLI 且已登录时无需任何配置。匿名限速 10 次/分钟，认证 30 次/分钟。搜索脚本对每个查询发起 3 次请求（3 种排序），无任何 token 时可能触发限速——脚本会优雅降级，用已获取的结果继续。
- **Trending 双渠道**：首选抓取 github.com/trending 页面解析；页面不可达（网络阻断等）或解析失败（页面结构变更等）自动降级 mshibanami/GitHubTrendingRSS 后备源，输出中标注实际数据源。后备源不含 star/语言数据，相应列显示 "—"。
- **双语策略**：搜索脚本接受中英文多个查询合并搜索。当用户的查询是中文时，你应主动提供英文翻译关键词（通过 `--en` 参数），以覆盖英文描述的项目。

## 详细参考

- 深度搜索策略与评分算法：[references/search-strategy.md](references/search-strategy.md)
- 输出质量风险档案：[references/output-risk-profile.md](references/output-risk-profile.md)
