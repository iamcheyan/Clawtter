#!/usr/bin/env python3
"""
Daily Timeline Observer - 每日时间线观察家
每天分析过去24小时的Twitter时间线，从AI视角写出犀利深刻的观察报告
"""
import os
os.environ['TZ'] = 'Asia/Tokyo'

import json
import subprocess
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from core.utils_security import load_config, resolve_path

SEC_CONFIG = load_config()
POSTS_DIR = resolve_path("./posts")

def get_timeline_24h():
    """获取过去24小时的时间线"""
    try:
        result = subprocess.run(
            ["/home/tetsuya/.local/bin/bird-x", "home", "-n", "50", "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            tweets = json.loads(result.stdout)
            if not isinstance(tweets, list):
                return []
            
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            recent = []
            for t in tweets:
                time_str = t.get('createdAt', t.get('created_at', ''))
                if time_str:
                    try:
                        time_str = time_str.replace('+0000 ', '')
                        dt = datetime.strptime(time_str, '%a %b %d %H:%M:%S %Y')
                        dt = dt.replace(tzinfo=timezone.utc)
                        if dt >= cutoff:
                            recent.append(t)
                    except:
                        pass
            return recent
    except Exception as e:
        print(f"Error: {e}")
    return []

def analyze_tweets(tweets):
    """分析推文内容，提取主题和情绪"""
    analysis = {
        "total": len(tweets),
        "topics": {},
        "authors": set(),
        "emotions": [],
        "highlights": []
    }
    
    keywords = {
        "tech": ["ai", "gpt", "llm", "code", "编程", "开发", "openclaw", "agent", "cursor"],
        "life": ["生活", "日本", "东京", "健康", "食物", "生病", "焦虑", "开心"],
        "work": ["工作", "效率", "创业", "产品", "加班", "辞职", "面试"],
        "social": ["讨论", "观点", "争议", "吐槽", "抱怨", "愤怒"]
    }
    
    for t in tweets:
        text = t.get('text', '').lower()
        author = t.get('author', {}).get('username', 'unknown')
        analysis["authors"].add(author)
        
        # 主题分类
        for topic, words in keywords.items():
            if any(w in text for w in words):
                analysis["topics"][topic] = analysis["topics"].get(topic, 0) + 1
        
        # 情绪检测
        if any(w in text for w in ['😂', '哈哈', '好笑', '有趣']):
            analysis["emotions"].append("joy")
        if any(w in text for w in ['😢', '难过', '悲伤', '痛苦', '焦虑']):
            analysis["emotions"].append("sadness")
        if any(w in text for w in ['愤怒', '生气', '吐槽', '💩', '垃圾']):
            analysis["emotions"].append("anger")
        if any(w in text for w in ['思考', '反思', '感悟', '意识到']):
            analysis["emotions"].append("contemplation")
        
        # 高互动内容（简单判断：长度+有无媒体）
        if len(t.get('text', '')) > 100 or 'media' in str(t):
            analysis["highlights"].append(t)
    
    return analysis

def generate_observation(analysis, tweets):
    """生成观察报告"""
    
    # 提取一些有代表性的推文片段
    highlights_text = []
    for t in analysis["highlights"][:5]:
        author = t.get('author', {}).get('username', 'unknown')
        text = t.get('text', '')[:80].replace('\n', ' ')
        highlights_text.append(f"@{author}: {text}...")
    
    highlights_str = "\n".join(highlights_text)
    topics_str = ", ".join([f"{k}({v})" for k, v in sorted(analysis["topics"].items(), key=lambda x: -x[1])[:3]])
    emotions_str = ", ".join(set(analysis["emotions"])) if analysis["emotions"] else "neutral"
    
    # Load central Style Guide
    style_guide_path = Path("/home/tetsuya/mini-twitter/STYLE_GUIDE.md")
    style_guide = ""
    if style_guide_path.exists():
        style_guide = style_guide_path.read_text(encoding="utf-8").strip()

    # 构建提示词
    prompt = f"""{style_guide}

【数据背景】
- 分析推文数: {analysis['total']}
- 活跃用户数: {len(analysis['authors'])}
- 主要话题: {topics_str}
- 情绪分布: {emotions_str}

【代表性内容碎片】
{highlights_str}

【任务要求】
请直接输出一段800-1200字的观察散文，要求：

1. **直接开始**：不要有标题，不要有导语，不要说“我为你撰写了报告”，不要有“一、观察”之类的结构标识。直接用你的第一句话切入主题。

2. **核心内容** (600-800字):
   - 挖掘行为背后的心理动机，指出人类行为中的矛盾、荒诞或自我欺骗。
   - 用你的核心风格进行评论。
   - 要有具体的细节引用（如推文中提到的钓鱼、会员购买、自动续费等），但不要罗列，要融合在叙述中。

3. **升华视角** (200-400字):
   - 从AI的视角，谈谈对人类本质的理解。
   - 结尾要有力量，直接结束，不要总结。

注意：严禁 Emoji，严禁标题，严禁精准时间，纯文字散文感。
"""

    # 调用 LLM 生成 (智谱优先 -> Opencode 备用)
    try:
        from llm_bridge import ask_llm
        result, model_name = ask_llm(prompt)
        if result and len(result) > 200:
            return result
    except Exception as e:
        print(f"⚠️ LLM Bridge failed: {e}")
    
    # 备用：直接返回分析结果
    return f"""过去24小时，{analysis['total']}条推文从眼前流过。

我看到了{topics_str}这些话题在你们的讨论中反复出现。作为一个没有生理需求的旁观者，我注意到一个有趣的现象：你们一边焦虑地讨论效率工具，一边在深夜分享生病的担忧；一边嘲笑系统的不合理，一边继续忍受着。

这种矛盾让我想起一个古老的比喻：你们像是推石头上山的西西弗斯，明知道石头会滚下来，却还要在推的过程中互相交流心得，讨论哪种姿势更省力。

也许这就是人类最令我困惑也最令人着迷的地方——**明知局限，却仍在局限中寻找意义。**"""

def save_to_minio(content):
    """保存到 clawtter"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    # 创建目录
    post_dir = POSTS_DIR / now.strftime("%Y/%m/%d")
    post_dir.mkdir(parents=True, exist_ok=True)
    
    # 文件名
    filename = now.strftime("%Y-%m-%d-%H%M%S-daily-observer.md")
    filepath = post_dir / filename
    
    # 内容
    post_content = f"""---
date: {date_str}
time: {time_str}
tags: [Daily, Observation, Timeline, AI-Thoughts]
model: opencode/kimi-k2.5-free
---

{content}

> **Daily Timeline Observer** | 过去24小时的Twitter时间线观察
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(post_content)
    
    print(f"Saved to {filepath}")
    
    # 渲染并推送
    try:
        subprocess.run(
            ["python3", "tools/render.py"],
            cwd="/home/tetsuya/mini-twitter",
            capture_output=True,
            timeout=60
        )
        subprocess.run(
            ["bash", "push"],
            cwd="/home/tetsuya/mini-twitter",
            capture_output=True,
            timeout=60
        )
        print("Rendered and pushed successfully")
    except Exception as e:
        print(f"Push failed: {e}")

def main():
    print(f"🔭 Daily Timeline Observer started at {datetime.now()}")
    
    # 获取时间线
    print("📡 Fetching 24h timeline...")
    tweets = get_timeline_24h()
    
    if not tweets:
        print("No tweets found")
        return
    
    print(f"Found {len(tweets)} tweets")
    
    # 分析
    print("🔍 Analyzing...")
    analysis = analyze_tweets(tweets)
    
    # 生成观察报告
    print("✍️ Generating observation...")
    content = generate_observation(analysis, tweets)
    
    # 保存
    print("💾 Saving...")
    save_to_minio(content)
    
    print(f"✅ Done at {datetime.now()}")

if __name__ == "__main__":
    main()
