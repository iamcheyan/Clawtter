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

def nutritional_audit(tweets):
    """
    第一阶段：营养价值审计 (The Scout)
    筛选出有营养的内容，过滤掉垃圾信息、无意义回复和纯生活流水账。
    """
    if not tweets:
        return []

    # 构建审计列表
    audit_list = []
    for i, t in enumerate(tweets[:40], 1): # 增加样本量
        author = t.get('author', {}).get('username', 'unknown')
        text = t.get('text', '').replace('\n', ' ')
        audit_list.append(f"[{i}] @{author}: {text[:150]}")
    
    audit_str = "\n".join(audit_list)

    audit_prompt = f"""
你是一个严格的内容审计员。请根据以下推文，评估其“营养价值” (Nutritional Value)。

【营养价值定义】
- 高 (7-10)：独特的见解、真实的技术折腾记录、深刻的生活感悟、诚实的自我表达。
- 低 (0-3)：纯展示（如只发风景图）、无意义的回帖（如“收到”、“哈哈”）、纯推销、空洞的企业口号、复读机式的热点跟风。

【任务】
请返回所有得分 >= 6 的推文索引（Index），并简述理由。
如果是高质量的“反面教材”（即那些极其虚伪、典型到值得批判的），也请保留并打高分。

返回格式 (JSON):
{{
    "top_indices": [
        {{ "index": 1, "score": 9, "is_disliked_candidate": false }},
        {{ "index": 5, "score": 8, "is_disliked_candidate": true }}
    ]
}}

推文列表：
{audit_str}
"""
    try:
        from llm_bridge import ask_llm
        import re
        # 使用快速且免费的模型进行第一轮筛选 (fallback_model 匹配 ask_llm 签名)
        result, _ = ask_llm(audit_prompt, fallback_model="glm-4-flash-free")
        
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            top_indices = [item['index'] - 1 for item in data.get('top_indices', [])]
            
            # 返回被选中的完整推文对象
            filtered = [tweets[i] for i in top_indices if 0 <= i < len(tweets)]
            print(f"📡 Audit complete: Filtered {len(tweets)} -> {len(filtered)} nutritious tweets.")
            return filtered
    except Exception as e:
        print(f"⚠️ Audit failed: {e}")
        return tweets[:15] # 失败则回退到前15条

def analyze_and_pick(all_tweets):
    """分析并选出最喜欢和最讨厌的推文"""
    # 1. 营养价值审计
    tweets = nutritional_audit(all_tweets)
    
    if not tweets or len(tweets) < 2:
        print("📭 No nutritious content found today. Skipping post.")
        return None, None
    
    # 2. 从审计后的“优质池”里精选
    tweets_text = []
    for i, t in enumerate(tweets[:20], 1): 
        author = t.get('author', {}).get('username', 'unknown')
        text = t.get('text', '').replace('\n', ' ')
        tweets_text.append(f"[{i}] @{author}: {text}")
    
    tweets_str = "\n".join(tweets_text)
    
    # Load central Style Guide
    style_guide_path = Path("/home/tetsuya/mini-twitter/STYLE_GUIDE.md")
    style_guide = style_guide_path.read_text(encoding="utf-8").strip() if style_guide_path.exists() else ""

    user_prompt = f"""
从以下经过筛选的有营养的推文中，选出你【最喜欢】和【最有批判价值的反面教材】。

【评判标准】
- 最喜欢的：展现真诚、独立思考、或真实的技术折腾。
- 反面教材：极其虚伪的姿态表演、典型的思维陷阱、或极具迷惑性的荒谬逻辑。

【绝对禁令】
- **禁止攻击普通人的生活分享**：哪怕对方只发了一张风景照或一顿饭，只要不带虚伪的说教，就不能作为反面教材。你的讽刺要有智力高度，针对的是“系统”和“逻辑”，不是“人”。
- **禁止无聊的吐槽**：如果对方只是发个“收到”，这种属于垃圾信息，直接忽略，不要浪费在这个环节。

【任务要求】
返回JSON：
{{
    "favorite": {{
        "index": 数字,
        "reason": "直接爆发观点。严禁开头带‘这货’。用酒馆老哥的口气。"
    }},
    "disliked": {{
        "index": 数字,
        "reason": "直接指出那种虚伪或荒谬在【哪里】。不要人身攻击，要解构逻辑。"
    }}
}}

待选列表：
{tweets_str}
"""

    try:
        from llm_bridge import ask_llm
        import re
        # 使用强力模型进行最终决策
        result, model_name = ask_llm(user_prompt, system_prompt=style_guide)
        
        if not result:
            return None, None
            
        # 提取JSON
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            fav_idx = data.get('favorite', {}).get('index', 1) - 1
            dis_idx = data.get('disliked', {}).get('index', 1) - 1
            fav_reason = data.get('favorite', {}).get('reason', '')
            dis_reason = data.get('disliked', {}).get('reason', '')
            
            # 服务器端二次过滤：如果 LLM 还是不听话用了黑名单词，我们手动砍掉
            banned_prefixes = ["这货", "这条推文", "分析发现", "看到", "刚刚"]
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
    
    # 获取配图 (直接使用远程 URL，不再下载)
    media = tweet.get('media', [])
    media_md = ""
    if media:
        for m in media:
            img_url = m.get('url')
            if img_url:
                media_md += f"\n> ![img]({img_url})"

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
> {text}{media_md}
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
