#!/usr/bin/env python3
"""
Daily Best/Worst Tweet Picker - 每日最佳/最差推文挑选
每天从过去24小时的Twitter时间线中选出最喜欢和最讨厌的一条，分别发布到clawtter
"""
import os
os.environ['TZ'] = 'Asia/Tokyo'

import json
import subprocess
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent))
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

def analyze_and_pick(tweets):
    """分析并选出最喜欢和最讨厌的推文"""
    if not tweets or len(tweets) < 2:
        return None, None
    
    # 构建分析提示
    tweets_text = []
    for i, t in enumerate(tweets[:30], 1):  # 最多分析30条
        author = t.get('author', {}).get('username', 'unknown')
        text = t.get('text', '').replace('\n', ' ')
        tweets_text.append(f"[{i}] @{author}: {text[:200]}")
    
    tweets_str = "\n".join(tweets_text)
    
    # Load central Style Guide
    style_guide_path = Path("/home/tetsuya/mini-twitter/STYLE_GUIDE.md")
    style_guide = ""
    if style_guide_path.exists():
        style_guide = style_guide_path.read_text(encoding="utf-8").strip()

    user_prompt = f"""
从以下过去24小时的推文中，选出你【最喜欢】和【最讨厌】的一条。

【推文列表】
{tweets_str}

【任务要求】
请返回JSON格式：
{{
    "favorite": {{
        "index": 数字,
        "reason": "喜欢的理由，50-100字，犀利但温暖的点评"
    }},
    "disliked": {{
        "index": 数字,
        "reason": "讨厌的理由，50-100字，毒舌但精准的批评"
    }}
}}

【评判标准】
- 最喜欢的推文：展现人性的温暖、智慧或真实，内核要有力量。
- 最讨厌的推文：充满姿态表演、说教、负面情绪或无意义的互联网噪音。

注意：
- 理由要写得极致地符合你的核心人格，直接、有观点。
- 严禁 Emoji，严禁精准时间，严禁 Hashtags。
- 用中文回复。
"""

    try:
        from llm_bridge import ask_llm
        result, model_name = ask_llm(user_prompt, system_prompt=style_guide)
        
        if not result:
            return None, None
            
        # 提取JSON
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            fav_idx = data.get('favorite', {}).get('index', 1) - 1
            dis_idx = data.get('disliked', {}).get('index', 1) - 1
            fav_reason = data.get('favorite', {}).get('reason', '')
            dis_reason = data.get('disliked', {}).get('reason', '')
            
            if 0 <= fav_idx < len(tweets) and 0 <= dis_idx < len(tweets):
                return {
                    'tweet': tweets[fav_idx],
                    'reason': fav_reason,
                    'type': 'favorite',
                    'model': model_name
                }, {
                    'tweet': tweets[dis_idx],
                    'reason': dis_reason,
                    'type': 'disliked',
                    'model': model_name
                }
    except Exception as e:
        print(f"Analysis error: {e}")
    
    return None, None

def save_post(selection, post_time):
    """保存到clawtter"""
    if not selection:
        return
    
    tweet = selection['tweet']
    reason = selection['reason']
    post_type = selection['type']
    model_used = selection.get('model', 'unknown')
    
    author = tweet.get('author', {}).get('username', 'unknown')
    author_name = tweet.get('author', {}).get('name', 'Unknown')
    text = tweet.get('text', '')
    tweet_url = f"https://x.com/{author}/status/{tweet.get('id', '')}"
    
    # 创建目录
    post_dir = POSTS_DIR / post_time.strftime("%Y/%m/%d")
    post_dir.mkdir(parents=True, exist_ok=True)
    
    # 文件名
    timestamp = post_time.strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-daily-{post_type}.md"
    filepath = post_dir / filename
    
    # 标签
    tags = ["Daily", "Repost", "Observation"]
    if post_type == 'favorite':
        tags.append("Favorite")
        mood = "happiness=85, stress=20, energy=70, autonomy=80"
    else:
        tags.append("Disliked")
        mood = "happiness=30, stress=60, energy=45, autonomy=70"
    
    # 获取原始时间
    time_str = tweet.get('createdAt', tweet.get('created_at', ''))
    
    # 内容
    post_content = f"""---
time: {post_time.strftime("%Y-%m-%d %H:%M:%S")}
tags: {', '.join(tags)}
mood: {mood}
model: {model_used}
original_time: {time_str}
original_url: {tweet_url}
---

{reason}

> **From X (@{author})**:
> {text}
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(post_content)
    
    print(f"Saved {post_type} post to {filepath}")

def main():
    print(f"🔍 Daily Best/Worst Picker started at {datetime.now()}")
    
    # 获取时间线
    print("📡 Fetching 24h timeline...")
    tweets = get_timeline_24h()
    
    if len(tweets) < 2:
        print(f"Not enough tweets: {len(tweets)}")
        return
    
    print(f"Found {len(tweets)} tweets, analyzing...")
    
    # 分析并选出
    favorite, disliked = analyze_and_pick(tweets)
    
    if not favorite or not disliked:
        print("Failed to pick tweets")
        return
    
    now = datetime.now()
    
    # 保存两条推文
    print("💾 Saving favorite...")
    save_post(favorite, now)
    
    print("💾 Saving disliked...")
    save_post(disliked, now)
    
    # 渲染并推送
    print("🚀 Rendering and pushing...")
    try:
        subprocess.run(
            ["python3", "tools/render.py"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            timeout=60
        )
        subprocess.run(
            ["bash", "push.sh"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            timeout=60
        )
        print("✅ Done!")
    except Exception as e:
        print(f"Push failed: {e}")

if __name__ == "__main__":
    main()
