# ai-edu-weekly · 国外 AI+教育新品每周看板

一个由 **GitHub Actions 定时任务**每周自动维护的看板：联网搜集海外 AI×教育领域的新产品，用 Claude 筛选后生成卡片。

## 工作方式

```
GitHub Actions（每周一 09:00 北京时间自动跑）
  └─ scripts/generate.py  → 调 Claude API + 联网搜索 → 筛选 6–8 款新品
       └─ 写入 data/weekly.json（prepend 本周一条）→ commit & push
              └─ index.html 读取 data/weekly.json 渲染
                    └─ GitHub Pages 托管 → 固定看板网址
```

- `index.html` —— 静态看板页，读取 `data/weekly.json`。**部署一次，之后不用改。**
- `data/weekly.json` —— 数据文件，Actions 每周往数组最前面加一条。
- `scripts/generate.py` —— 调研脚本（Claude API + web_search 工具）。
- `.github/workflows/weekly.yml` —— 定时工作流（cron + 手动触发）。

## 使用前需要配置

在仓库 **Settings → Secrets and variables → Actions → New repository secret** 里添加：

| Secret 名 | 值 |
|---|---|
| `ANTHROPIC_API_KEY` | 你的 Claude API Key（在 https://console.anthropic.com 生成，按用量付费） |

## 手动触发一次

仓库 **Actions** 标签页 → 左侧「每周更新看板」→ 右侧 **Run workflow**。

## 数据格式

`weekly.json` 是数组，每个元素是一周：

```json
{
  "week": "2026-W29",
  "date_range": "2026-07-13 ~ 2026-07-19",
  "generated_at": "2026-07-20",
  "items": [
    {
      "name": "产品名",
      "url": "https://产品官网",
      "country": "美国",
      "category": "AI 助教 / 作业批改",
      "one_liner": "一句话它是做什么的",
      "why_it_matters": "从 PM 视角为什么值得看",
      "source": "Product Hunt",
      "source_url": "https://来源链接"
    }
  ]
}
```

## 本地预览

```bash
cd ai-edu-weekly && python3 -m http.server 8080
# 打开 http://localhost:8080
```
