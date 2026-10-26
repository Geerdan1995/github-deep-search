#!/usr/bin/env python3
"""GitHub Deep Search — 深度搜索 GitHub 开源项目

多策略深度搜索：合并 best-match / stars / updated 三种排序结果，去重打分，
支持中英文双语查询自动合并。仅依赖 Python 标准库。

用法:
  python github_search.py "机器学习框架" --en "machine learning framework" --limit 10
  python github_search.py "web framework" --language python --limit 15 --json
  python github_search.py --doctor

认证（按优先级自动探测）:
  --token 参数 > GITHUB_TOKEN 环境变量 > gh CLI 登录态 > 匿名
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

GITHUB_API = "https://api.github.com"
USER_AGENT = "github-deep-search/1.1"


# ───────────────────────── HTTP 层 ─────────────────────────

def _request(url, token=None, timeout=30):
    """发起 HTTP 请求并返回 JSON。"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_chinese(text):
    """检测文本是否包含中文字符。"""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


# ───────────────────────── 认证层 ─────────────────────────

def resolve_token(cli_token=None):
    """token 获取链: --token 参数 > GITHUB_TOKEN 环境变量 > gh CLI 登录态 > 匿名。

    返回 (token, source_label)；匿名时 token 为 None。
    """
    if cli_token:
        return cli_token, "--token 参数"
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token, "GITHUB_TOKEN 环境变量"
    gh_path = shutil.which("gh")
    if gh_path:
        try:
            result = subprocess.run(
                [gh_path, "auth", "token"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                token = result.stdout.strip()
                if token:
                    return token, "gh CLI 登录态"
        except (subprocess.TimeoutExpired, OSError):
            pass
    return None, "匿名（限速 10次/分）"


def _gh_account():
    """取 gh CLI 登录账号名（仅用于提示，失败返回 None）。"""
    gh_path = shutil.which("gh")
    if not gh_path:
        return None
    try:
        result = subprocess.run(
            [gh_path, "api", "user", "--jq", ".login"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def run_doctor(token, source_label):
    """安装自检：Python 版本 / 网络 / 认证 / Search API 限额。返回退出码。"""
    ok = True
    lines = []

    v = sys.version_info
    if v >= (3, 8):
        lines.append(f"[✓] Python {v.major}.{v.minor}.{v.micro} (≥3.8)")
    else:
        ok = False
        lines.append(f"[✗] Python {v.major}.{v.minor}.{v.micro}（需要 ≥3.8）")

    # /rate_limit 端点不计入限额，兼测网络与配额
    rate = None
    try:
        t0 = time.monotonic()
        rate = _request(f"{GITHUB_API}/rate_limit", token=token, timeout=10)
        ms = int((time.monotonic() - t0) * 1000)
        lines.append(f"[✓] 网络可达 api.github.com ({ms}ms)")
    except urllib.error.HTTPError as e:
        ok = False
        if e.code == 401:
            lines.append(f"[✗] token 无效（api.github.com 返回 401，来源: {source_label}）")
        else:
            lines.append(f"[✗] api.github.com 返回 HTTP {e.code}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        ok = False
        lines.append(f"[✗] 无法连接 api.github.com: {e}")
        lines.append("    提示: 本机若开着代理（Clash/v2ray 等），规则模式常不代理终端流量——")
        lines.append("    可开全局模式，或设 HTTP_PROXY/HTTPS_PROXY 环境变量，或用 --proxy http://127.0.0.1:端口 重试")

    if token:
        if source_label == "gh CLI 登录态":
            account = _gh_account()
            lines.append(
                f"[✓] gh CLI 已登录 ({account}) → 将自动使用其 token"
                if account else "[✓] gh CLI 已登录 → 将自动使用其 token"
            )
        else:
            lines.append(f"[✓] 已启用 token（来源: {source_label}）")
    elif shutil.which("gh"):
        lines.append("[i] gh CLI 已安装但未登录（可选；gh auth login 后自动提速）")
    else:
        lines.append("[i] 未检测到 token / gh CLI（可选；匿名限速 10次/分）")

    if rate:
        search = rate.get("resources", {}).get("search", {})
        remaining = search.get("remaining", "?")
        limit = search.get("limit", "?")
        reset = search.get("reset")
        if reset:
            reset_str = time.strftime("（重置于 %H:%M UTC）", time.gmtime(reset))
        else:
            reset_str = ""
        lines.append(f"[✓] Search API 限额: {remaining}/{limit} 剩余{reset_str}")

    p = urllib.request.getproxies().get("https") or urllib.request.getproxies().get("http")
    if p:
        lines.append(f"[i] 代理: {p}")

    print("\n".join(lines))
    print("—— 一切就绪。" if ok else "—— 存在问题，按上面提示排查。")
    return 0 if ok else 1


# ───────────────────────── 搜索层 ─────────────────────────

def search_repositories(query, language=None, sort="best-match", order="desc",
                        per_page=30, token=None):
    """调用 GitHub Search API 搜索单个查询。"""
    q = query.strip()
    if language:
        q += f" language:{language}"
    params = {
        "q": q,
        "sort": sort,
        "order": order,
        "per_page": min(per_page, 100),
    }
    url = f"{GITHUB_API}/search/repositories?{urllib.parse.urlencode(params)}"
    try:
        data = _request(url, token=token)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            body = e.read().decode("utf-8", errors="replace")
            print(f"[!] API 速率限制: {body[:200]}", file=sys.stderr)
            if not token:
                print("[!] 提示: 设置 GITHUB_TOKEN 环境变量可提升速率限制", file=sys.stderr)
            return {"items": [], "total_count": 0, "rate_limited": True}
        raise
    data.setdefault("items", [])
    data.setdefault("total_count", 0)
    return data


def _normalize_repo(item, query_terms):
    """将 API 返回的 item 标准化为统一结构并打分。"""
    full_name = item.get("full_name", "")
    name = item.get("name", "")
    description = item.get("description") or ""
    stars = item.get("stargazers_count", 0)
    forks = item.get("forks_count", 0)
    updated_at = item.get("updated_at", "")
    pushed_at = item.get("pushed_at", updated_at)
    language = item.get("language") or "N/A"
    topics = item.get("topics", [])
    html_url = item.get("html_url", "")
    open_issues = item.get("open_issues_count", 0)
    watchers = item.get("watchers_count", stars)
    license_info = item.get("license")
    license_name = license_info.get("name", "N/A") if license_info else "N/A"
    archived = item.get("archived", False)

    # ── 打分 ──
    score = 0.0
    # star 权重（对数压缩，避免超高 star 项目垄断）
    score += math.log10(stars + 1) * 10
    # fork 权重
    score += math.log10(forks + 1) * 3

    # 近期活跃度加分
    now = datetime.now(timezone.utc)
    try:
        push_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        days_since = (now - push_dt).days
        if days_since <= 30:
            score += 25
        elif days_since <= 90:
            score += 12
        elif days_since <= 180:
            score += 6
        elif days_since > 365:
            score -= 5  # 长期不活跃扣分
    except (ValueError, TypeError):
        pass

    # 名称/描述匹配加分
    name_lower = name.lower()
    desc_lower = description.lower()
    for term in query_terms:
        tl = term.lower()
        if tl in name_lower:
            score += 15
        if tl in desc_lower:
            score += 8
        # topic 匹配
        if tl in [t.lower() for t in topics]:
            score += 10

    # 归档项目扣分
    if archived:
        score -= 30

    return {
        "full_name": full_name,
        "name": name,
        "description": description,
        "stars": stars,
        "forks": forks,
        "language": language,
        "updated_at": updated_at,
        "pushed_at": pushed_at,
        "topics": topics,
        "html_url": html_url,
        "open_issues": open_issues,
        "watchers": watchers,
        "license": license_name,
        "archived": archived,
        "_score": round(score, 2),
    }


def deep_search(queries, language=None, limit=15, token=None):
    """多策略深度搜索：合并多种排序 × 多个查询，去重打分。

    Args:
        queries: 查询词列表（可包含中文和英文）
        language: 编程语言过滤
        limit: 最终返回数量
        token: GitHub token
    """
    # 收集所有查询词用于匹配打分
    query_terms = set()
    for q in queries:
        query_terms.update(q.lower().split())

    # 搜索策略：对每个查询用 3 种排序各搜一次
    strategies = [
        ("best-match", "desc"),
        ("stars", "desc"),
        ("updated", "desc"),
    ]

    seen = {}          # full_name -> normalized repo
    rate_limited = False

    for query in queries:
        for sort, order in strategies:
            result = search_repositories(
                query, language=language, sort=sort, order=order,
                per_page=30, token=token,
            )
            if result.get("rate_limited"):
                rate_limited = True
                continue

            for item in result.get("items", []):
                repo = _normalize_repo(item, query_terms)
                fn = repo["full_name"]
                if fn in seen:
                    # 已存在则取较高分
                    if repo["_score"] > seen[fn]["_score"]:
                        seen[fn] = repo
                else:
                    seen[fn] = repo

            # 礼貌延迟，避免触发速率限制
            if not token:
                time.sleep(1.2)
            else:
                time.sleep(0.4)

    # 按分数排序
    ranked = sorted(seen.values(), key=lambda r: r["_score"], reverse=True)
    return ranked[:limit], {
        "total_found": len(seen),
        "rate_limited": rate_limited,
        "queries": queries,
        "language": language,
    }


# ───────────────────────── 格式化层 ─────────────────────────

def _fmt_count(n):
    """格式化数字：1234 -> 1.2k, 1234000 -> 1.2M。"""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _fmt_date(iso_str):
    """ISO 日期 -> YYYY-MM-DD。"""
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str[:10] if len(iso_str) >= 10 else "N/A"


def format_markdown(results, meta):
    """将搜索结果格式化为 Markdown 表格。"""
    lines = []
    lines.append(f"## GitHub 深度搜索结果\n")
    queries_str = " / ".join(f"`{q}`" for q in meta["queries"])
    lines.append(f"**查询词**: {queries_str}")
    if meta.get("language"):
        lines.append(f"**语言筛选**: {meta['language']}")
    lines.append(f"**去重后总计**: {meta['total_found']} 个项目，展示 Top {len(results)}\n")

    if meta.get("rate_limited"):
        lines.append("> ⚠️ 部分请求触发 API 速率限制，结果可能不完整。"
                     "设置 `GITHUB_TOKEN` 环境变量可提升限制。\n")

    if not results:
        lines.append("未找到匹配项目。建议：")
        lines.append("- 尝试更宽泛的关键词")
        lines.append("- 移除语言筛选")
        lines.append("- 使用英文关键词重试")
        return "\n".join(lines)

    header = "| # | 项目 | 描述 | ⭐ Stars | 🍴 Forks | 语言 | 最近更新 |"
    sep = "|---|------|------|---------|---------|------|---------|"
    lines.append(header)
    lines.append(sep)

    for i, r in enumerate(results, 1):
        desc = r["description"][:80] + ("…" if len(r["description"]) > 80 else "")
        desc = desc.replace("|", "\\|") or "—"
        name_display = f"[{r['full_name']}]({r['html_url']})"
        lines.append(
            f"| {i} | {name_display} | {desc} | "
            f"{_fmt_count(r['stars'])} | {_fmt_count(r['forks'])} | "
            f"{r['language']} | {_fmt_date(r['pushed_at'])} |"
        )

    return "\n".join(lines)


def format_json(results, meta):
    """将搜索结果格式化为 JSON。"""
    output = {
        "meta": meta,
        "results": [
            {
                "rank": i,
                "full_name": r["full_name"],
                "name": r["name"],
                "description": r["description"],
                "url": r["html_url"],
                "stars": r["stars"],
                "forks": r["forks"],
                "language": r["language"],
                "last_push": r["pushed_at"],
                "last_updated": r["updated_at"],
                "topics": r["topics"],
                "license": r["license"],
                "open_issues": r["open_issues"],
                "archived": r["archived"],
                "relevance_score": r["_score"],
            }
            for i, r in enumerate(results, 1)
        ],
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


# ───────────────────────── CLI ─────────────────────────

def main():
    # Windows 控制台默认 GBK，防止 ✓/中文/emoji 输出崩
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    parser = argparse.ArgumentParser(
        description="GitHub 深度搜索 — 多策略合并去重，中英文双语",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python github_search.py "机器学习框架" --en "machine learning framework"
  python github_search.py "web framework" --language python --limit 20
  python github_search.py --doctor
  python github_search.py "web framework" --proxy http://127.0.0.1:7890
        """,
    )
    parser.add_argument("query", nargs="?", default=None,
                        help="主搜索关键词（可为中文）；与 --doctor 二选一")
    parser.add_argument("--doctor", action="store_true",
                        help="安装自检：Python/网络/认证/限额，不执行搜索")
    parser.add_argument("--en", dest="en_query", default=None,
                        help="英文关键词（可选，用于双语合并搜索）")
    parser.add_argument("--language", "-l", default=None,
                        help="编程语言筛选（如 python, go, rust）")
    parser.add_argument("--limit", "-n", type=int, default=15,
                        help="返回结果数量（默认 15）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出")
    parser.add_argument("--token", default=None,
                        help="GitHub token（默认自动探测: GITHUB_TOKEN 环境变量 > gh CLI 登录态）")
    parser.add_argument("--proxy", default=None, metavar="URL",
                        help="HTTP 代理，如 http://127.0.0.1:7890（规则模式代理不覆盖终端时用）")

    args = parser.parse_args()

    if args.proxy:
        proxy = args.proxy if "://" in args.proxy else f"http://{args.proxy}"
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        if not args.doctor:
            print(f"[i] 代理: {proxy}", file=sys.stderr)

    if not args.doctor and not args.query:
        parser.error("必须提供搜索关键词，或使用 --doctor 自检")

    token, auth_label = resolve_token(args.token)

    if args.doctor:
        sys.exit(run_doctor(token, auth_label))

    # 构建查询列表：中文 + 英文（去重）
    queries = [args.query]
    if args.en_query and args.en_query.lower() not in [q.lower() for q in queries]:
        queries.append(args.en_query)

    # 如果主查询是中文且未提供英文查询，提示
    if _is_chinese(args.query) and not args.en_query:
        print("[i] 检测到中文查询但未提供 --en 参数。"
              "建议添加 --en 英文关键词以获得更全面的搜索结果。", file=sys.stderr)

    print(f"[i] 认证: {auth_label}", file=sys.stderr)
    print(f"[i] 深度搜索中... 查询: {queries}", file=sys.stderr)

    try:
        results, meta = deep_search(queries, language=args.language,
                                    limit=args.limit, token=token)
    except OSError as e:  # URLError 亦为 OSError 子类，含连接重置/超时
        print(f"[!] 网络错误: {e}", file=sys.stderr)
        print("[!] 提示: 若本机开着代理（Clash/v2ray 等），规则模式常不代理终端流量——"
              "可开全局模式，或设 HTTP_PROXY/HTTPS_PROXY，或用 --proxy http://127.0.0.1:端口 重试",
              file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(format_json(results, meta))
    else:
        print(format_markdown(results, meta))


if __name__ == "__main__":
    main()
