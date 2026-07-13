# ai-edu-weekly · 国外 AI+教育新品每周看板

一个由**定时云端 Agent** 每周自动维护的看板：搜集海外 AI×教育领域的新产品，筛选后生成卡片。

## 工作方式

- `index.html` —— 静态看板页，读取 `data/weekly.json` 渲染。**只需部署一次，之后不用改。**
- `data/weekly.json` —— 数据文件。云端 Agent 每周往数组里 **prepend 一条本周记录**（一次 commit）。
- GitHub Pages 托管 `index.html`，得到一个固定网址即看板。

## 数据格式

`weekly.json` 是一个数组，每个元素是一周：

```json
{
  "week": "2026-W29",
  "date_range": "2026-07-13 ~ 2026-07-19",
  "generated_at": "2026-07-20 09:00 CST",
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

因为页面用 `fetch` 读 JSON，直接双击 `index.html` 会被浏览器 CORS 拦。用本地小服务器看：

```bash
cd ai-edu-weekly && python3 -m http.server 8080
# 浏览器打开 http://localhost:8080
```
