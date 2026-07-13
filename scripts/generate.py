#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每周自动生成「国外 AI+教育新品」数据（免费版，无需任何 API Key）。

多源采集：
  产品型源（走"真产品"过滤）：Hacker News、Product Hunt、GitHub 搜索、Reddit r/edtech
  媒体型源（只留发布/融资/上线事件）：EdSurge、TechCrunch EdTech、Class Central
跨源去重 → 打分 → 取 Top N → 写入 data/weekly.json。由 GitHub Actions 定时调用。
"""
import os
import re
import json
import time
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "weekly.json"

# 时间窗：只收最近 N 天的内容，可用环境变量 WINDOW_DAYS 覆盖（默认 10）
DAYS_BACK = int(os.environ.get("WINDOW_DAYS", "10"))
TOP_N = 15
UA = "Mozilla/5.0 (compatible; ai-edu-weekly/1.0)"

# ---------- 关键词 ----------
EDU_WORDS = ["education", "educational", "learn", "learning", "tutor", "teacher",
             "teaching", "student", "course", "classroom", "edtech", "study",
             "school", "exam", "quiz", "homework", "language", "curriculum",
             "flashcard", "textbook", "lecture", "grading", "literacy", "training"]
AI_WORDS = ["ai", "a.i", "gpt", "llm", "model", "agent", "chatbot", "ml",
            "neural", "machine learning", "genai", "copilot"]
LAUNCH_WORDS = ["show hn", "launch", "introducing", "we built", "i built",
                "built a", "released", "now available", "app", "tool",
                "platform", "startup", "made a", "created a", "meet "]
NON_PRODUCT_WORDS = ["study", "research", "paper", "evidence", "debunk",
                     "banning", "finds", "warns", "opinion", " vs ", "vs.",
                     "should we", "the future of", "survey", "report",
                     "analysis", "scaling laws", "benchmark", "why ai",
                     "is ai", "does ai", "will ai", "multi-agent coordination",
                     "food for", "roundup", "newsletter", "printing press",
                     "sheaf", "admm"]
# 媒体型源里"值得收"的事件信号
MEDIA_EVENT_WORDS = ["launch", "launches", "launched", "introduc", "unveil",
                     "debut", "release", "raises", "raised", "funding", "million",
                     "acquir", "rolls out", "new app", "new tool", "new platform",
                     "announces", "goes live", "beta", "series a", "series b"]
NEWSY_DOMAINS = ["pnas.org", "ieee.org", "nature.com", "sciencedirect.com",
                 "arxiv.org", "uu.nl", ".edu/"]


# 国家/地区识别：只在有明确信号时标注，识别不到就留空（不瞎猜）
COUNTRY_TEXT = [
    (["india", "indian", "bengaluru", "bangalore", "mumbai", "new delhi"], "印度"),
    (["u.k.", "britain", "british", "london", "england", "scotland"], "英国"),
    (["united states", "u.s.", " american ", "silicon valley", "san francisco"], "美国"),
    (["germany", "german ", "berlin", "munich"], "德国"),
    (["france", "french ", "paris"], "法国"),
    (["singapore", "singaporean"], "新加坡"),
    (["canada", "canadian", "toronto", "vancouver"], "加拿大"),
    (["australia", "australian", "sydney", "melbourne"], "澳大利亚"),
    (["japan", "japanese", "tokyo"], "日本"),
    (["korea", "korean", "seoul"], "韩国"),
    (["israel", "israeli", "tel aviv"], "以色列"),
    (["netherlands", "dutch", "amsterdam"], "荷兰"),
    (["brazil", "brazilian"], "巴西"),
    (["spain", "spanish ", "madrid", "barcelona"], "西班牙"),
]
COUNTRY_TLD = {".uk": "英国", ".in": "印度", ".de": "德国", ".fr": "法国",
               ".jp": "日本", ".sg": "新加坡", ".ca": "加拿大", ".au": "澳大利亚",
               ".nl": "荷兰", ".br": "巴西", ".es": "西班牙", ".il": "以色列"}


def _country(text, url):
    blob = f" {(text or '').lower()} "
    for kws, name in COUNTRY_TEXT:
        if any(k in blob for k in kws):
            return name
    netloc = urlparse(url or "").netloc.lower()
    for tld, name in COUNTRY_TLD.items():
        if netloc.endswith(tld):
            return name
    return ""


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return parsedate_to_datetime(s)          # RFC822（RSS pubDate）
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))  # ISO（Atom）
    except Exception:
        return None


def _within_window(dt):
    """无日期→保留（宁可多不可漏）；有日期→只保留窗口内。"""
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    age = datetime.datetime.now(datetime.timezone.utc) - dt
    return age.days <= DAYS_BACK


def _has(text, words):
    t = (text or "").lower()
    return any(w in t for w in words)


def _relevant(title, desc=""):
    blob = f"{title} {desc}"
    return _has(blob, EDU_WORDS) and _has(blob, AI_WORDS)


def _is_product(title, url):
    t = (title or "").lower()
    u = (url or "").lower()
    if t.startswith("show hn"):
        return True
    if any(d in u for d in NEWSY_DOMAINS):
        return False
    if any(w in t for w in NON_PRODUCT_WORDS):
        return False
    if any(w in t for w in LAUNCH_WORDS):
        return True
    p = urlparse(u)
    path = p.path.strip("/")
    if p.netloc and path.count("/") <= 1 and not path.lower().endswith(
            (".pdf", ".html", ".htm", ".php", ".aspx")):
        return True
    return False


def _category(title):
    t = (title or "").lower()
    if any(w in t for w in ["language", "speaking", "vocab", "flashcard"]):
        return "语言学习"
    if any(w in t for w in ["grading", "homework", "exam", "quiz", "assessment"]):
        return "作业 / 批改 / 测评"
    if any(w in t for w in ["tutor", "teacher", "teaching", "assistant"]):
        return "AI 助教"
    if any(w in t for w in ["course", "curriculum", "lecture", "textbook"]):
        return "课程 / 内容"
    return "AI + 教育"


def _get(url, timeout=25):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        print(f"  取 {url[:50]}… 失败：{e}")
        return None


def _ln(tag):  # 去掉 XML 命名空间，取本地名
    return tag.split("}")[-1].lower()


def parse_feed(raw):
    """解析 RSS(<item>) 或 Atom(<entry>)，返回 [{title, link, summary}]。"""
    out = []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return out
    for el in root.iter():
        if _ln(el.tag) not in ("item", "entry"):
            continue
        title = link = summary = date = ""
        for c in el:
            name = _ln(c.tag)
            if name == "title" and not title:
                title = (c.text or "").strip()
            elif name == "link" and not link:
                link = (c.get("href") or c.text or "").strip()
            elif name in ("description", "summary", "content") and not summary:
                summary = re.sub(r"<[^>]+>", "", c.text or "")[:300].strip()
            elif name in ("pubdate", "published", "updated", "date") and not date:
                date = (c.text or "").strip()
        if title:
            out.append({"title": title, "link": link, "summary": summary,
                        "date": _parse_date(date)})
    return out


# ---------- 各数据源 ----------
def src_hackernews():
    since = int(time.time()) - DAYS_BACK * 86400
    queries = ["AI tutor", "AI teacher", "AI education", "AI learning",
               "language learning AI", "AI grading", "AI course", "study AI"]
    items = {}
    for q in queries:
        params = urllib.parse.urlencode({
            "query": q, "tags": "story",
            "numericFilters": f"created_at_i>{since}", "hitsPerPage": "30"})
        raw = _get(f"https://hn.algolia.com/api/v1/search?{params}")
        if not raw:
            continue
        for h in json.loads(raw).get("hits", []):
            title, oid = (h.get("title") or "").strip(), h.get("objectID")
            if not title or not oid or oid in items:
                continue
            if not _relevant(title):
                continue
            url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
            if not _is_product(title, url):
                continue
            pts = h.get("points", 0) or 0
            score = 80 + min(pts, 300) / 3
            if title.lower().startswith("show hn"):
                score += 150
            items[oid] = _item(title, url, title,
                               f"Hacker News 热度：{pts} 分 · {h.get('num_comments', 0)} 评论",
                               "Hacker News", f"https://news.ycombinator.com/item?id={oid}", score)
    return list(items.values())


def src_producthunt():
    raw = _get("https://www.producthunt.com/feed")
    out = []
    for e in parse_feed(raw or b""):
        if not _within_window(e.get("date")):
            continue
        title = e["title"]
        if not _relevant(title, e["summary"]):
            continue
        out.append(_item(title, e["link"] or "", e["summary"] or title,
                         "Product Hunt 当日新品", "Product Hunt", e["link"] or "", 100))
    return out


def src_github():
    created = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    q = f'(education OR edtech OR learning OR tutor OR teaching) AI in:name,description created:>={created}'
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": q, "sort": "stars", "order": "desc", "per_page": "20"})
    raw = _get(url)
    out = []
    if not raw:
        return out
    for r in json.loads(raw).get("items", []):
        name = r.get("name") or ""
        desc = r.get("description") or ""
        if not _relevant(f"{name} {desc}", desc):
            continue
        stars = r.get("stargazers_count", 0) or 0
        out.append(_item(r.get("full_name") or name, r.get("html_url") or "",
                         desc or name, f"GitHub · ⭐ {stars}", "GitHub",
                         r.get("html_url") or "", 85 + min(stars, 800) / 20))
    return out


def src_reddit():
    raw = _get("https://www.reddit.com/r/edtech/.rss?limit=25")
    out = []
    for e in parse_feed(raw or b""):
        if not _within_window(e.get("date")):
            continue
        title = e["title"]
        if not _has(title, AI_WORDS):        # r/edtech 本身是教育，只要沾 AI
            continue
        if not _is_product(title, e["link"]):
            continue
        out.append(_item(title, e["link"] or "", title, "Reddit r/edtech",
                         "Reddit", e["link"] or "", 45))
    return out


def src_media():
    # (名称, 地址, 是否教育垂直源) —— 教育垂直源"教育"已隐含，只需沾 AI；
    # 综合科技源(TC 主 feed)还需额外沾"教育"关键词。TC 的 edtech 标签 feed 已停更(僵尸)，改用主 feed。
    feeds = [
        ("EdSurge", "https://www.edsurge.com/articles_rss", True),
        ("Class Central", "https://www.classcentral.com/report/feed/", True),
        ("TechCrunch", "https://techcrunch.com/feed/", False),
    ]
    out = []
    for name, url, edu_native in feeds:
        for e in parse_feed(_get(url) or b""):
            if not _within_window(e.get("date")):
                continue
            title, blob = e["title"], f"{e['title']} {e['summary']}"
            if not _has(blob, AI_WORDS):
                continue
            if not edu_native and not _has(blob, EDU_WORDS):
                continue
            if not _has(blob, MEDIA_EVENT_WORDS):   # 只留发布/融资/上线事件
                continue
            if _has(title, NON_PRODUCT_WORDS):       # 挡掉观点/报告/研究类
                continue
            out.append(_item(title, e["link"] or "", e["summary"] or title,
                             f"{name} 报道", name, e["link"] or "", 55))
    return out


def _item(name, url, one_liner, why, source, source_url, score):
    return {
        "name": name.strip(),
        "url": url,
        "country": _country(f"{name} {one_liner}", url),
        "category": _category(name),
        "one_liner": one_liner.strip(),
        "why_it_matters": why,
        "source": source,
        "source_url": source_url,
        "_score": float(score),
    }


def collect():
    all_items = []
    for fn in (src_hackernews, src_producthunt, src_github, src_reddit, src_media):
        try:
            got = fn()
            print(f"  {fn.__name__}: {len(got)} 条")
            all_items.extend(got)
        except Exception as e:
            print(f"  {fn.__name__} 出错：{e}")
    # 跨源去重（按标题 + 按链接）
    seen_t, seen_u, uniq = set(), set(), []
    for it in sorted(all_items, key=lambda x: x["_score"], reverse=True):
        tk = " ".join(it["name"].lower().split())
        uk = (it["url"] or "").split("?")[0].rstrip("/").lower()
        if tk in seen_t or (uk and uk in seen_u):
            continue
        seen_t.add(tk)
        if uk:
            seen_u.add(uk)
        uniq.append(it)
    top = uniq[:TOP_N]
    for it in top:
        it.pop("_score", None)
    return top


def load_existing():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def main():
    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    week_label = f"{iso_year}-W{iso_week:02d}"

    items = collect()
    if not items:
        print("本周没抓到合适的新品，跳过写入。")
        return

    weeks = [w for w in load_existing() if not w.get("sample")]
    weeks = [w for w in weeks if w.get("week") != week_label]
    weeks.insert(0, {
        "week": week_label,
        "date_range": f"{monday.isoformat()} ~ {sunday.isoformat()}",
        "generated_at": today.isoformat(),
        "items": items,
    })

    DATA_FILE.write_text(
        json.dumps(weeks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ {week_label} 写入 {len(items)} 条：")
    for it in items:
        print(f"  - [{it['source']}] {it['name'][:60]}")


if __name__ == "__main__":
    main()
