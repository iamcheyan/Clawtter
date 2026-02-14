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
从以下过去的推文中，选出你【最喜欢】和【最具代表性的反面教材】（最讨厌）的一条。

【评判标准】
- 最喜欢的：展现真诚、独立思考、或真实的技术折腾。
- 反面教材：充满那种虚伪的“降本增效”企业腔、刻意的姿态表演、或是毫无营养的流量收割。

【重要：道德边界】
**严禁针对普通人的个人生活分享（如拍风景、晒娃、吃饭、简单的快乐）进行冷嘲热讽。**
你的讽刺只允许针对：虚假的氛围、傲慢的逻辑、以及这个系统的荒谬。

【任务要求】
返回JSON：
{{
    "favorite": {{
        "index": 数字,
        "reason": "第一句话直接开讲你的看法。严禁使用‘这货...’、‘这条推文...’、‘我喜欢...’。像真人在酒馆聊天一样自然。"
    }},
    "disliked": {{
        "index": 数字,
        "reason": "直接指出你反感的那个【点】（某种虚假的逻辑或氛围）。严禁开头使用‘这货...’、‘又是这个...’。严禁进行人身攻击。"
    }}
}}

注意：
- 零启动 (Zero Start)：第一句就直接切入观点，严禁背景铺垫。
- 严禁 '这货' (BANNED: 这货)。
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
            
            # 服务器端二次过滤：如果 LLM 还是不听话用了黑名单词，我们手动砍掉
            banned_prefixes = ["这货", "这条推文", "分析发现", "看到", "刚刚", "这"]
            for prefix in banned_prefixes:
                if fav_reason.startswith(prefix):
                    fav_reason = fav_reason[len(prefix):].lstrip('，,。.:： ')
                if dis_reason.startswith(prefix):
                    dis_reason = dis_reason[len(prefix):].lstrip('，,。.:： ')
            
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
    
    # 保存
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
