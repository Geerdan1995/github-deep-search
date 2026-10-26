# 深度搜索策略与评分算法

本文档说明 `github_search.py` 的搜索策略和相关性评分机制。

## 多策略搜索

对每个查询词（中文 + 英文），脚本发起 3 次 API 请求，使用不同的排序策略：

| 策略 | sort 参数 | 目的 |
|------|----------|------|
| best-match | `best-match` | GitHub 默认相关性排序，捕捉语义最匹配的项目 |
| stars | `stars` | 按 star 数降序，捕捉最流行的项目 |
| updated | `updated` | 按最近更新降序，捕捉最活跃的项目 |

三种策略的结果合并去重（以 `full_name` 为唯一键），确保覆盖面最大化：
- best-match 擅长找到名称/描述精准匹配的项目
- stars 擅长找到高人气的成熟项目
- updated 擅长找到近期活跃的新项目

## 双语合并

用户查询为中文时，脚本同时接受英文关键词（`--en` 参数），对两个查询分别执行 3 策略搜索，共 6 次 API 请求，结果统一合并去重。

这样设计的原因：
- GitHub 上大量优质项目的描述是英文的，纯中文搜索会遗漏
- 中文关键词在 GitHub 上仍有价值（部分项目有中文描述或 README）
- 双语合并取并集，覆盖最广

## 相关性评分

合并去重后，每个项目按以下公式打分排序：

```
score = star_weight + fork_weight + recency_bonus + match_bonus + archive_penalty
```

| 因素 | 计算 | 权重 | 说明 |
|------|------|------|------|
| star_weight | `log10(stars + 1) × 10` | 高 | 对数压缩，避免超高 star 项目垄断排名 |
| fork_weight | `log10(forks + 1) × 3` | 中 | fork 数反映实际使用程度 |
| recency_bonus | ≤30天 +25, ≤90天 +12, ≤180天 +6, >365天 -5 | 中高 | 近期活跃的项目优先 |
| match_bonus | 名称命中 +15, 描述命中 +8, topic 命中 +10 | 中 | 关键词出现在项目名/描述/topic 中加分 |
| archive_penalty | 归档项目 -30 | 高 | 已归档项目降权 |

## 速率限制处理

- 匿名调用：10 次/分钟，每次最多 30 条结果
- 认证调用（GITHUB_TOKEN）：30 次/分钟，每次最多 100 条结果
- 脚本在每次请求间加入礼貌延迟（匿名 1.2s，认证 0.4s）
- 触发限速时优雅降级：跳过该请求，用已获取结果继续打分排序
- 输出中标注 `⚠️ 部分请求触发 API 速率限制`

## GitHub Search API 参考

- 端点：`GET https://api.github.com/search/repositories`
- 文档：https://docs.github.com/en/rest/search/search#search-repositories
- 查询语法支持：`language:python`、`stars:>1000`、`pushed:>2026-01-01`、`topic:ai` 等
- 响应字段：`full_name`、`description`、`stargazers_count`、`forks_count`、`html_url`、`updated_at`、`pushed_at`、`language`、`topics`、`license`、`archived`
