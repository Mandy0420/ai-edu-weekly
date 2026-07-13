#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每周自动生成「国外 AI+教育新品」数据（免费版，无需任何 API Key）。
数据源：Hacker News（Algolia 免费 API），关键词筛「AI × 教育」相关的新帖，
按热度排序取 Top N，写入 data/weekly.json。由 GitHub Actions 定时调用。
"""
import json
import time
import datetime
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "weekly.json"

DAYS_BACK = 10
TOP_N = 12

# 组合查询：既沾 AI 又沾教育，结果本身就比较对口
QUERIES = [
    "AI tutor", "AI teacher", "AI education", "AI learning",
    "language learning AI", "AI grading", "AI classroom",
    "edtech AI", "AI course", "study AI", "AI quiz", "AI homework",
]

# 关键词桶（用于判定相关性 + 粗分类）
EDU_WORDS = ["education", "educational", "learn", "learning", "tutor", "teacher",
             "teaching", "student", "course", "classroom", "edtech", "study",
             "school", "exam", "quiz", "homework", "language", "curriculum",
             "flashcard", "textbook", "lecture", "grading"]
AI_WORDS = ["ai", "a.i", "gpt", "llm", "model", "agent", "chatbot", "ml",
            "neural", "machine learning", "genai", "copilot"]

# 偏"研究/新闻"而非"产品"的站点，降权
NEWSY_DOMAINS = ["pnas.org", "ieee.org", "nature.com", "sciencedirect.com",
                 "arxiv.org", "theregister.com", "sfgate.com", "nytimes.com",
                 "thenewstack.io", "northwestern.edu", ".edu/", "uu.nl",
                 "washingtonpost.com", "theguardian.com", "reuters.com"]


def _has(text, words):
    t = text.lower()
    return any(w in t for w in words)


def _score(title, url, points):
    """偏向真实产品/发布：Show HN 和产品站加分，纯新闻/论文降权。"""
    s = float(points or 0)
    t = title.lower()
    if t.startswith("show hn"):
        s += 150
    if any(w in t for w in ["launch", "introducing", "built", "we built", "app", "tool", "platform"]):
        s += 25
    if any(d in (url or "").lower() for d in NEWSY_DOMAINS):
        s -= 120
    if any(w in t for w in ["study", "research", "paper", "evidence", "banning", "debunk"]):
        s -= 60
    return s


def _category(title):
    t = title.lower()
    if any(w in t for w in ["language", "speaking", "vocab", "flashcard"]):
        return "语言学习"
    if any(w in t for w in ["grading", "homework", "exam", "quiz", "assessment"]):
        return "作业 / 批改 / 测评"
    if any(w in t for w in ["tutor", "teacher", "teaching", "assistant"]):
        return "AI 助教"
    if any(w in t for w in ["course", "curriculum", "lecture", "textbook"]):
        return "课程 / 内容"
    return "AI + 教育"


def fetch_hn():
    since = int(time.time()) - DAYS_BACK * 86400
    seen = {}
    seen_titles = set()
    for q in QUERIES:
        params = urllib.parse.urlencode({
            "query": q,
            "tags": "story",
            "numericFilters": f"created_at_i>{since}",
            "hitsPerPage": "30",
        })
        url = f"https://hn.algolia.com/api/v1/search?{params}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ai-edu-weekly/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except Exception as e:
            print(f"  查询 '{q}' 失败：{e}")
            continue
        for h in data.get("hits", []):
            title = (h.get("title") or "").strip()
            oid = h.get("objectID")
            if not title or not oid:
                continue
            # 相关性：标题里要沾教育，且沾 AI
            if not (_has(title, EDU_WORDS) and _has(title, AI_WORDS)):
                continue
            norm = " ".join(title.lower().split())
            if oid in seen or norm in seen_titles:
                continue
            seen_titles.add(norm)
            seen[oid] = {
                "name": title,
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                "country": "",
                "category": _category(title),
                "one_liner": title,
                "why_it_matters": f"Hacker News 热度：{h.get('points', 0)} 分 · {h.get('num_comments', 0)} 评论",
                "source": "Hacker News",
                "source_url": f"https://news.ycombinator.com/item?id={oid}",
                "_score": _score(title, h.get("url"), h.get("points", 0)),
            }
    items = sorted(seen.values(), key=lambda x: x["_score"], reverse=True)[:TOP_N]
    for it in items:
        it.pop("_score", None)
    return items


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

    items = fetch_hn()
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
        json.dumps(weeks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"✅ {week_label} 写入 {len(items)} 条：")
    for it in items:
        print(f"  - {it['name'][:70]}  [{it['category']}]")


if __name__ == "__main__":
    main()
