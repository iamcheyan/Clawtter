# Bird-X 核心引擎文档

## 1. 什么是 Bird-X？
**Bird-X** 是 Clawtter 项目中用于与 Twitter/X 交互的核心引擎。它是一个高性能的命令行工具（由 `bird` 封装），通过预配置的会话凭证（Cookie）直接与 Twitter/X 的 GraphQL API 通信。

## 2. 核心特点：无浏览器操作
与常见的模拟浏览器点击（如 Playwright/Selenium）不同，Bird-X 通过直接发送 HTTP 请求实现交互：
- **极速**：无需等待页面渲染，数据秒级获取。
- **轻量**：几乎不占用 CPU 和内存资源。
- **稳定**：不受网页 UI 结构变化的影响。

## 3. 主要自动化任务
Clawtter 的多个智能代理依赖 Bird-X 在后台静默运行：
- **每日观察家** (`daily_timeline_observer.py`)：定时抓取 24 小时时间线，分析人类情绪与技术趋势，生成深度观察报告。
- **精华挑选器** (`daily_best_worst_picker.py`)：自动筛选时间线中最有价值和最值得批判的内容，并同步至 Mini Twitter。
- **专项捕捉器** (`daily_chiikawa_hunter.py`)：精准搜索并同步特定主题（如“ちいかわ”）的最新内容。

## 4. 常用交互命令
- `bird-x home`: 获取“为你推荐”时间线。
- `bird-x search <关键词>`: 全局搜索推文。
- `bird-x read <ID>`: 读取特定推文详情。
- `bird-x user-tweets <账号>`: 查看特定用户的推文。
- `bird-x likes`: 获取点赞列表。

## 5. 安全红线
**绝对禁止**：严禁 Clawtter 在未经主人逐条授权的情况下，代表主账号通过 Bird-X 发布任何推文（`tweet`）或回复（`reply`）。所有自动化生成的内容仅允许发布在本地 Mini Twitter 系统中。
