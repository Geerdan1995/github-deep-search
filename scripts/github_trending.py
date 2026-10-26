#!/usr/bin/env python3
"""GitHub Trending — 热门开源项目榜单抓取

抓取 github.com/trending 页面，解析热门项目列表。
支持按时间范围（daily/weekly/monthly）和编程语言筛选。
HTML 解析失败时自动降级 mshibanami/GitHubTrendingRSS 后备源。
仅依赖 Python 标准库。

用法:
  python github_trending.py                          # 今日热榜（全部语言）
  python github_trending.py --since weekly           # 本周热榜
  python github_trending.py --since monthly --language python  # 本月 Python 热榜
  python github_trending.py --since weekly --json    # JSON 输出
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser

TRENDING_URL = "https://github.com/trending"
RSS_BASE = "https://mshibanami.github.io/GitHubTrendingRSS"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

SINCE_MAP = {
    "daily": "daily",
    "today": "daily",
    "weekly": "weekly",
    "week": "weekly",
    "monthly": "monthly",
    "month": "monthly",
}


# ───────────────────────── HTML 抓取 ─────────────────────────

def fetch_trending(since="weekly", language=None, spoken_language=None, timeout=30):
    """抓取 GitHub Trending 页面 HTML。"""
    params = {"since": since}
    if language:
        params["language"] = language
    if spoken_language:
        params["spoken_language_code"] = spoken_language

    url = f"{TRENDING_URL}?{urllib.parse.urlencode(params)}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return html


# ───────────────────────── HTML 解析 ─────────────────────────

class TrendingParser(HTMLParser):
    """解析 GitHub Trending 页面，提取项目信息。

    GitHub Trending 页面结构（每个项目为一个 <article> 块）：
      <article class="Box-row">
        <h2><a href="/owner/repo">owner / repo</a></h2>
        <p>描述文本</p>
        <div>
          <span itemprop="programmingLanguage">Python</span>
          <a href="/owner/repo/stargazers">12,345</a>
          <a href="/owner/repo/forks">1,234</a>
          <span>567 stars this week</span>
        </div>
      </article>
    """

    def __init__(self):
        super().__init__()
        self.repos = []
        self._repo = None
        self._tag_stack = []
        self._in_article = False
        self._in_h2 = False
        self._in_desc_p = False
        self._capture_text = False
        self._text_buf = []
        self._link_href = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        # 进入 article（每个 trending 项目）
        if tag == "article" and "Box-row" in cls:
            self._in_article = True
            self._repo = {
                "full_name": "",
                "description": "",
                "language": "",
                "stars": 0,
                "forks": 0,
                "stars_added": 0,
                "stars_added_period": "",
            }
            return

        if not self._in_article:
            return

        self._tag_stack.append(tag)

        # 标题中的仓库链接
        if tag in ("h1", "h2") and "lh-condensed" in cls:
            self._in_h2 = True
            return

        if tag == "a" and self._in_h2:
            href = attrs_dict.get("href", "")
            if href.startswith("/") and "/stargazers" not in href and "/forks" not in href:
                self._repo["full_name"] = href.strip("/")

        # 描述段落
        if tag == "p" and "col-9" in cls:
            self._in_desc_p = True
            self._capture_text = True
            self._text_buf = []
            return

        # 编程语言
        if tag == "span" and attrs_dict.get("itemprop") == "programmingLanguage":
            self._capture_text = True
            self._text_buf = []
            return

        # star / fork 计数链接
        if tag == "a":
            href = attrs_dict.get("href", "")
            if "/stargazers" in href:
                self._capture_text = True
                self._text_buf = []
                self._link_href = "stars"
            elif "/forks" in href or "/members" in href:
                self._capture_text = True
                self._text_buf = []
                self._link_href = "forks"
            elif "Link--muted" in cls:
                # 备用：其他 muted 链接可能是 star/fork
                self._capture_text = True
                self._text_buf = []
                self._link_href = "link-muted"

    def handle_endtag(self, tag):
        if not self._in_article:
            return

        if tag in ("h1", "h2") and self._in_h2:
            self._in_h2 = False
            return

        if tag == "p" and self._in_desc_p:
            self._repo["description"] = " ".join(self._text_buf).strip()
            self._in_desc_p = False
            self._capture_text = False
            self._text_buf = []
            return

        if tag == "span" and self._capture_text and not self._repo["language"]:
            text = " ".join(self._text_buf).strip()
            if text and text not in ("", "Built by"):
                self._repo["language"] = text
            self._capture_text = False
            self._text_buf = []
            return

        if tag == "a" and self._capture_text:
            text = "".join(self._text_buf).strip().replace(",", "")
            if text.isdigit():
                num = int(text)
                if self._link_href == "stars":
                    self._repo["stars"] = num
                elif self._link_href == "forks":
                    self._repo["forks"] = num
                elif self._link_href == "link-muted":
                    # 推断：第一个 muted link 通常是 stars，第二个是 forks
                    if self._repo["stars"] == 0:
                        self._repo["stars"] = num
                    elif self._repo["forks"] == 0:
                        self._repo["forks"] = num
            self._capture_text = False
            self._text_buf = []
            self._link_href = None
            return

        if tag == "article":
            self._in_article = False
            if self._repo and self._repo["full_name"]:
                self.repos.append(self._repo)
            self._repo = None

        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._capture_text:
            self._text_buf.append(data)
        # 捕获 "stars this week" 等文本
        if self._in_article and not self._capture_text:
            m = re.search(r"([\d,]+)\s+stars?\s+(today|this week|this month)", data)
            if m and self._repo:
                self._repo["stars_added"] = int(m.group(1).replace(",", ""))
                self._repo["stars_added_period"] = m.group(2)


def parse_trending_html(html):
    """解析 trending HTML，返回项目列表。"""
    parser = TrendingParser()
    parser.feed(html)

    # 后处理：补充 URL、清理描述
    for repo in parser.repos:
        repo["html_url"] = f"https://github.com/{repo['full_name']}"
        repo["description"] = re.sub(r"\s+", " ", repo["description"]).strip()
        if not repo["language"]:
            repo["language"] = "N/A"

    return parser.repos


# ───────────────────────── RSS 后备层 ─────────────────────────

def fetch_trending_rss(since="weekly", language=None, timeout=30):
    """从 mshibanami/GitHubTrendingRSS 抓取后备数据（XML 文本）。

    语言子源不存在时自动退到全语言源。返回 (xml_text, url)。
    """
    lang = (language or "").strip().lower() or "all"
    candidates = [f"{RSS_BASE}/{since}/{lang}.xml"]
    if lang != "all":
        candidates.append(f"{RSS_BASE}/{since}/all.xml")
    last_err = None
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace"), url
        except OSError as e:  # URLError 亦为 OSError 子类
            last_err = e
    raise last_err


def _extract_description(desc_html):
    """从 RSS description 的 HTML 片段里取第一段纯文本（即仓库描述）。"""
    if not desc_html:
        return ""
    m = re.search(r"<p>(.*?)</p>", desc_html, re.DOTALL)
    text = m.group(1) if m else desc_html
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_trending_rss(xml_text, max_items=25):
    """解析 GitHubTrendingRSS 的 RSS 2.0，返回与 HTML 解析同构的项目列表。

    条目的 title 为 "owner/repo"（兼容旧格式 "owner/repo : description"），
    description 为 HTML 片段（首个 <p> 是仓库描述）；不含 star/fork/语言数据，
    相应字段填 0 / N/A，由输出层显示为 "—"。
    """
    repos = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if " : " in title:
            full_name, description = title.split(" : ", 1)
            full_name = full_name.strip()
            description = description.strip()
        else:
            full_name = title
            description = _extract_description(item.findtext("description") or "")
        if not full_name and link.startswith("https://github.com/"):
            full_name = link[len("https://github.com/"):].strip("/")
        if not full_name or "/" not in full_name:
            continue
        repos.append({
            "full_name": full_name,
            "description": description,
            "language": "N/A",
            "stars": 0,
            "forks": 0,
            "stars_added": 0,
            "stars_added_period": "",
            "html_url": link or f"https://github.com/{full_name}",
        })
        if len(repos) >= max_items:
            break
    return repos


# ───────────────────────── 格式化层 ─────────────────────────

def _fmt_count(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def format_markdown(repos, since, language, source="GitHub Trending 页面"):
    """将热榜格式化为 Markdown 表格。"""
    period_map = {
        "daily": "今日",
        "weekly": "本周",
        "monthly": "本月",
    }
    period = period_map.get(since, since)
    title = f"## GitHub Trending — {period}热榜\n"

    lang_str = f"**语言**: {language}\n" if language else "**语言**: 全部\n"
    lines = [title, lang_str, f"**数据源**: {source}\n", f"**项目数**: {len(repos)}\n"]

    if not repos:
        lines.append("未获取到热榜数据。可能原因：")
        lines.append("- GitHub 页面结构变更（需更新解析器）")
        lines.append("- 网络连接问题")
        lines.append("- 该语言暂无 trending 数据")
        return "\n".join(lines)

    header = "| # | 项目 | 描述 | ⭐ 总Star | 📈 本期增长 | 🍴 Forks | 语言 |"
    sep = "|---|------|------|---------|------------|---------|------|"
    lines.append(header)
    lines.append(sep)

    for i, r in enumerate(repos, 1):
        desc = r["description"][:70] + ("…" if len(r["description"]) > 70 else "")
        desc = desc.replace("|", "\\|") or "—"
        name_display = f"[{r['full_name']}]({r['html_url']})"
        stars = _fmt_count(r["stars"]) if r["stars"] else "—"
        forks = _fmt_count(r["forks"]) if r["forks"] else "—"
        growth = f"+{_fmt_count(r['stars_added'])}" if r["stars_added"] else "—"
        lines.append(
            f"| {i} | {name_display} | {desc} | "
            f"{stars} | {growth} | "
            f"{forks} | {r['language']} |"
        )

    return "\n".join(lines)


def format_json(repos, since, language, source="GitHub Trending 页面"):
    """JSON 输出。"""
    output = {
        "since": since,
        "language": language or "all",
        "source": source,
        "count": len(repos),
        "repos": [
            {
                "rank": i,
                "full_name": r["full_name"],
                "url": r["html_url"],
                "description": r["description"],
                "language": r["language"],
                "stars": r["stars"],
                "stars_added": r["stars_added"],
                "stars_added_period": r["stars_added_period"],
                "forks": r["forks"],
            }
            for i, r in enumerate(repos, 1)
        ],
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


# ───────────────────────── CLI ─────────────────────────

def main():
    # Windows 控制台默认 GBK，防止中文/emoji 输出崩
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    parser = argparse.ArgumentParser(
        description="GitHub Trending 热榜抓取 — 按时间范围和语言筛选",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python github_trending.py                          # 今日热榜
  python github_trending.py --since weekly           # 本周热榜
  python github_trending.py --since monthly -l python # 本月 Python 热榜
  python github_trending.py --since weekly --json    # JSON 输出
        """,
    )
    parser.add_argument("--since", "-s", default="weekly",
                        choices=["daily", "weekly", "monthly", "today", "week", "month"],
                        help="时间范围: daily(今日) / weekly(本周) / monthly(本月)，默认 weekly")
    parser.add_argument("--language", "-l", default=None,
                        help="编程语言筛选（如 python, go, rust, javascript）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出")
    parser.add_argument("--proxy", default=None, metavar="URL",
                        help="HTTP 代理，如 http://127.0.0.1:7890（规则模式代理不覆盖终端时用）")

    args = parser.parse_args()

    if args.proxy:
        proxy = args.proxy if "://" in args.proxy else f"http://{args.proxy}"
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        print(f"[i] 代理: {proxy}", file=sys.stderr)

    since = SINCE_MAP.get(args.since, args.since)

    print(f"[i] 抓取 GitHub Trending... since={since}, language={args.language or 'all'}",
          file=sys.stderr)

    source = "GitHub Trending 页面"
    repos = []
    try:
        html = fetch_trending(since=since, language=args.language)
        repos = parse_trending_html(html)
        print(f"[i] 解析到 {len(repos)} 个项目", file=sys.stderr)
    except OSError as e:  # URLError 亦为 OSError 子类，含连接重置/超时
        print(f"[!] GitHub 页面抓取失败: {e}", file=sys.stderr)

    if not repos:
        print("[!] 主渠道无结果，尝试 RSS 后备源...", file=sys.stderr)
        try:
            xml_text, rss_url = fetch_trending_rss(since=since, language=args.language)
            repos = parse_trending_rss(xml_text)
            source = "RSS 后备（GitHub 页面不可达或解析失败）"
            print(f"[i] RSS 后备源: {rss_url}，解析到 {len(repos)} 个项目", file=sys.stderr)
        except (OSError, ET.ParseError) as e:
            print(f"[!] RSS 后备也失败: {e}", file=sys.stderr)
            print("[!] 提示: 若本机开着代理（Clash/v2ray 等），规则模式常不代理终端流量——"
                  "可开全局模式，或设 HTTP_PROXY/HTTPS_PROXY，或用 --proxy http://127.0.0.1:端口 重试",
                  file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(format_json(repos, since, args.language, source))
    else:
        print(format_markdown(repos, since, args.language, source))


if __name__ == "__main__":
    main()
