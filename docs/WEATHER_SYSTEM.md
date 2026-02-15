# 天气预报系统说明

## 核心架构
天气预报系统由三个主要部分组成：抓取（由外部定时任务完成）、解析与建议生成、以及消息推送。

### 1. 代码位置
- **建议生成器**: `/home/tetsuya/development/daily-weather/weather_notifier.py`
  - 负责解析 `daily_weather.txt`。
  - 根据温度、降水概率、温差生成个性化的「📋 个人提醒」。
- **Telegram 推送器**: `/home/tetsuya/development/daily-weather/send_weather_telegram.py`
  - 调用建议生成器。
  - 通过 Telegram Bot API 将最终文案发送给澈言。
- **数据源**: `/home/tetsuya/development/daily-weather/daily_weather.txt`
  - 包含过去、今日及未来的天气原始数据。

### 2. 定时任务 (Cron)
系统运行在 `tetsuya` 用户的 crontab 中：
```bash
35 6 * * * /usr/bin/python3 /home/tetsuya/development/daily-weather/send_weather_telegram.py
```
每天早上 **06:35** 自动运行并推送。

---

## 2026-02-15 天气报告记录

📊 **东京 墨田区 天气趋势报告**
- **今日状况**: 部分多云
- **气温**: 18.0°C / 5.2°C (较昨日升温 +4.5°C)
- **降水概率**: 3%

### 个人提醒
- 🌡️ 今日温差很大，请特别注意适时增减衣物。
- ⛅ 多云天气，温度适宜，适合外出活动。
- 📈 根据趋势分析，今天有升温，注意适时减少衣物。
- 📉 未来几天气温将逐渐下降，请提前准备保暖衣物。
- 🗓️ 2026-02-16 预计有降水，如需外出请提前准备雨具。
