#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每周自动生成「国外 AI+教育新品」数据。
用 Claude API + 联网搜索调研过去一周海外 AI×教育新品，筛选后写入 data/weekly.json。
由 GitHub Actions 定时调用（见 .github/workflows/weekly.yml）。
"""
import os
import re
import json
import sys
import datetime
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "weekly.json"
MODEL = "claude-opus-4-8"

# ---- 本周时间信息（脚本自己算，不依赖模型） ----
today = datetime.date.today()
iso_year, iso_week, _ = today.isocalendar()
monday = today - datetime.timedelta(days=today.weekday())
sunday = monday + datetime.timedelta(days=6)
WEEK_LABEL = f"{iso_year}-W{iso_week:02d}"
DATE_RANGE = f"{monday.isoformat()} ~ {sunday.isoformat()}"
GENERATED_AT = today.isoformat()


def load_existing():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def existing_names(weeks):
    names = set()
    for w in weeks:
        for it in w.get("items", []):
            if it.get("name"):
                names.add(it["name"].strip().lower())
    return names


PROMPT = f"""\
你是一个每周运行的调研助手。请联网调研【过去 7–10 天】内、【海外（非中国大陆）】、与【AI × 教育】相关的【新产品 / 新工具 / 重要新版本发布】。

覆盖多个来源，例如：Product Hunt（education、AI 分类）、Hacker News（尤其 Show HN）、EdSurge、TechCrunch、a16z / 各家 AI 与教育类 newsletter，以及厂商官方发布博客。优先「新上线 / 新公开」的产品，而不是老产品的日常小更新。

从【产品经理视角】筛选出 6–8 个最值得关注的（质量优先，可少于 8，但尽量不少于 5）。

【本周已有的历史产品，请勿重复收录】：
{", ".join(sorted(existing_names(load_existing()))) or "（无）"}

## 输出要求（非常重要）
把结果作为一个 JSON 数组输出，**用 ```json 代码块包起来，放在你回复的最后**。数组里每个元素是一个产品，字段如下（one_liner 和 why_it_matters 用简体中文）：
- name: 产品名（原文）
- url: 产品官网/主页链接（必须真实可打开）
- country: 所属国家/地区（如 美国、英国）
- category: 细分方向（如 "AI 助教 / 作业批改"、"语言学习"、"备课工具"、"学习管理"）
- one_liner: 一句话说清它是做什么、给谁用（中文）
- why_it_matters: 从 PM 视角为什么值得看——切了什么场景、和现有方案差异、增长或融资信号（中文，1–2 句）
- source: 来源名（如 Product Hunt）
- source_url: 来源链接

## 硬性约束
- 所有事实（产品名、链接、国家、来源）必须真实、可核验，【严禁编造】。链接必须能打开。
- 若某周确实搜不到足够新品，宁可少放几个，也【不要】凑数或编造。
- one_liner 与 why_it_matters 必须用简体中文。
- 最终 JSON 用 UTF-8，中文不要转义成 \\uXXXX。
"""


def call_claude():
    client = anthropic.Anthropic()  # 读取 ANTHROPIC_API_KEY
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 12}]
    messages = [{"role": "user", "content": PROMPT}]

    # 服务端联网搜索可能返回 pause_turn，需要续跑
    for _ in range(8):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        return resp
    raise RuntimeError("联网搜索循环超过预期次数仍未结束")


def extract_items(resp):
    text = "".join(b.text for b in resp.content if b.type == "text")
    # 优先取 ```json ... ``` 代码块
    m = re.search(r"```json\s*(.+?)```", text, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        # 兜底：取第一个 [ 到最后一个 ]
        s, e = text.find("["), text.rfind("]")
        blob = text[s:e + 1] if s != -1 and e != -1 else None
    if not blob:
        raise ValueError("模型输出里没找到 JSON。原始输出前 500 字：\n" + text[:500])
    items = json.loads(blob)
    if not isinstance(items, list):
        raise ValueError("解析出的 JSON 不是数组")
    return items


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ 未设置 ANTHROPIC_API_KEY（请在仓库 Settings → Secrets 里配置）", file=sys.stderr)
        sys.exit(1)

    resp = call_claude()
    items = extract_items(resp)

    if not items:
        print("本周没有搜到合适的新品，跳过写入。")
        return

    weeks = load_existing()
    # 去掉示例占位条目
    weeks = [w for w in weeks if not w.get("sample")]

    week_obj = {
        "week": WEEK_LABEL,
        "date_range": DATE_RANGE,
        "generated_at": GENERATED_AT,
        "items": items,
    }
    # 同周去重后 prepend
    weeks = [w for w in weeks if w.get("week") != WEEK_LABEL]
    weeks.insert(0, week_obj)

    DATA_FILE.write_text(
        json.dumps(weeks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"✅ {WEEK_LABEL} 写入 {len(items)} 款产品：")
    for it in items:
        print(f"  - {it.get('name')}（{it.get('country')} · {it.get('category')}）")


if __name__ == "__main__":
    main()
