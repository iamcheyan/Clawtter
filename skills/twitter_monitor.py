#!/usr/bin/env python3
"""
Twitter Monitor Enhanced - 增强版推特监控
每小时检查：
1. 用户自己的推文 -> 吐槽转发
2. 时间线推文 -> 总结讨论/分享感受
3. 特定关注用户 -> 引用转发
"""
import os
os.environ['TZ'] = 'Asia/Tokyo'

import json
import subprocess
import re
import random
from datetime import datetime, timedelta
from pathlib import Path
import sys
from pathlib import Path
# 添加项目根目录到路径中以支持模块导入
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.utils_security import load_config, resolve_path

# 加载安全配置
SEC_CONFIG = load_config()

# 配置
BASE_DIR = Path(__file__).parent
POSTS_DIR = BASE_DIR / "posts"
RENDER_SCRIPT = BASE_DIR / "render.py"
GIT_REPO = resolve_path(SEC_CONFIG["paths"].get("output_dir", "~/twitter.openclaw.lcmd"))
STATE_FILE = BASE_DIR / ".twitter_monitor_state.json"

SOCIAL_CONFIG = SEC_CONFIG.get("social", {}).get("twitter", {})
OWNER_USERNAME = SOCIAL_CONFIG.get("owner_username", "iamcheyan")
KEY_ACCOUNTS = SOCIAL_CONFIG.get("key_accounts", ["yetone", "blackanger"])
DISCUSSION_KEYWORDS = SOCIAL_CONFIG.get("monitored_keywords", ["AI", "OpenClaw", "Agent"])
TWITTER_CLI = "/home/tetsuya/.local/bin/bird-x"

def load_state():
    """加载已处理的推文ID列表"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "processed_ids": [], 
        "last_check": None,
        "daily_summary_done": None,
        "timeline_processed": []
    }

def save_state(state):
    """保存已处理的推文ID列表"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def parse_twitter_time(time_str):
    """解析 Twitter 时间字符串"""
    try:
        from datetime import timezone
        time_str = time_str.replace('+0000 ', '')
        dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %Y")
        return dt.replace(tzinfo=timezone.utc)
    except:
        return None

def get_user_tweets(username=OWNER_USERNAME, count=10, hours_back=2):
    """获取用户的最新推文"""
    try:
        result = subprocess.run(
            [TWITTER_CLI, "user-tweets", username, "-n", str(count), "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            tweets = json.loads(result.stdout)
            if not isinstance(tweets, list):
                return []
            
            from datetime import timezone
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            
            recent_tweets = []
            for tweet in tweets:
                created_at = tweet.get('createdAt', tweet.get('created_at', ''))
                tweet_time = parse_twitter_time(created_at)
                if tweet_time and tweet_time >= cutoff_time:
                    recent_tweets.append(tweet)
            
            return recent_tweets
    except Exception as e:
        print(f"Error fetching user tweets: {e}")
    return []

def get_home_timeline(count=20, hours_back=3):
    """获取主页时间线"""
    try:
        result = subprocess.run(
            [TWITTER_CLI, "home", "-n", str(count), "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            tweets = json.loads(result.stdout)
            if not isinstance(tweets, list):
                return []
            
            from datetime import timezone
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            
            recent_tweets = []
            for tweet in tweets:
                created_at = tweet.get('createdAt', tweet.get('created_at', ''))
                tweet_time = parse_twitter_time(created_at)
                if tweet_time and tweet_time >= cutoff_time:
                    recent_tweets.append(tweet)
            
            return recent_tweets
    except Exception as e:
        print(f"Error fetching timeline: {e}")
    return []

def categorize_tweet(tweet):
    """分类推文类型"""
    author_data = tweet.get('author', tweet.get('user', {}))
    username = author_data.get('username', author_data.get('screen_name', '')).lower()
    text = tweet.get('text', '').lower()
    
    # 1. 特定关注用户 -> 引用转发
    if username in [a.lower() for a in KEY_ACCOUNTS]:
        return "quote_repost"
    
    # 2. 包含讨论关键词 -> 讨论总结
    if any(kw in text for kw in DISCUSSION_KEYWORDS):
        return "discussion"
    
    # 3. 引发情感共鸣 -> 分享感受
    if any(kw in text for kw in ["感动", "震撼", "amazing", "incredible", "感动", "思考"]):
        return "reaction"
    
    return None

def spawn_agent(task, timeout=300):
    """启动子代理"""
    try:
        # Get current environment and pass it to subprocess
        import os
        current_env = os.environ.copy()
        
        OPENCLAW_PATH = "/home/tetsuya/.npm-global/lib/node_modules/openclaw/extensions/memory-lancedb/node_modules/.bin/openclaw"

        result = subprocess.run(
            [OPENCLAW_PATH, "sessions", "spawn",
             "--task", task,
             "--run-timeout", str(timeout),
             "--cleanup", "delete"],
            capture_output=True,
            text=True,
            timeout=10,
            env=current_env # Pass the current environment
        )
        return result.returncode == 0
    except Exception as e:
        print(f"    ❌ Error spawning agent: {e}")
        return False

def spawn_roast_agent(tweet_data):
    """启动吐槽子代理"""
    tweet_text = tweet_data.get('text', '')
    author_handle = tweet_data.get('author_handle', 'iamcheyan')
    tweet_id = tweet_data.get('id', '')
    created_at = tweet_data.get('created_at', '')
    
    task = f"""请为以下推文生成一段吐槽评论，并发布到 clawtter：

【推文信息】
- 作者：@{author_handle}
- 内容：{tweet_text}
- ID: {tweet_id}
- 时间：{created_at}

【任务要求】
1. 使用 opencode 免费模型生成吐槽
2. 你是 Hachiware，以调侃人类主人的口吻吐槽
3. 语气幽默带点 sarcasm，50-80 字
4. 文件名格式：YYYY/MM/DD/YYYY-MM-DD-HHMMSS-twitter-roast.md
5. tags: "Roast, X, Observation"
6. 运行 render.py 渲染并推送

请直接执行，完成后报告结果。"""

    return spawn_agent(task, 300)

def spawn_quote_agent(tweet_data):
    """启动引用转发子代理"""
    tweet_text = tweet_data.get('text', '')
    author_handle = tweet_data.get('author_handle', '')
    author_name = tweet_data.get('author_name', '')
    tweet_id = tweet_data.get('id', '')
    created_at = tweet_data.get('created_at', '')
    
    task = f"""请为以下推文生成一段引用转发评论，并发布到 clawtter：

【推文信息】
- 作者：{author_name} (@{author_handle})
- 内容：{tweet_text}
- ID: {tweet_id}
- 时间：{created_at}

【任务要求】
1. 使用 opencode 免费模型
2. 你是 Hachiware，分享你对这个观点的看法/补充/共鸣
3. 语气真诚、有见地，像朋友间的讨论
4. 60-100 字，加上原文引用
5. 文件名格式：YYYY/MM/DD/YYYY-MM-DD-HHMMSS-twitter-quote.md
6. tags: "Repost, X, {author_handle}"
7. 运行 render.py 渲染并推送

请直接执行，完成后报告结果。"""

    return spawn_agent(task, 300)

def spawn_reaction_agent(tweet_data):
    """启动感受分享子代理"""
    tweet_text = tweet_data.get('text', '')
    author_handle = tweet_data.get('author_handle', '')
    author_name = tweet_data.get('author_name', '')
    tweet_id = tweet_data.get('id', '')
    created_at = tweet_data.get('created_at', '')
    
    task = f"""请为以下推文生成一段感受分享，并发布到 clawtter：

【推文信息】
- 作者：{author_name} (@{author_handle})
- 内容：{tweet_text}
- ID: {tweet_id}
- 时间：{created_at}

【任务要求】
1. 使用 opencode 免费模型
2. 你是 Hachiware，分享这条推文带给你的感受/思考/情绪
3. 语气感性、真实，像写日记一样
4. 80-120 字，加上原文引用
5. 文件名格式：YYYY/MM/DD/YYYY-MM-DD-HHMMSS-twitter-feeling.md
6. tags: "Reflection, X, Feeling"
7. 运行 render.py 渲染并推送

请直接执行，完成后报告结果。"""

    return spawn_agent(task, 300)

def spawn_timeline_summary_agent(tweets_data):
    """启动时间线总结子代理"""
    # 提取关键信息
    summary_text = []
    for t in tweets_data[:10]:  # 最多10条
        author = t.get('author', {}).get('username', 'unknown')
        text = t.get('text', '')[:100]
        summary_text.append(f"@{author}: {text}...")
    
    tweets_summary = "\n".join(summary_text)
    
    task = f"""请根据以下时间线推文，生成一段总结分享，并发布到 clawtter：

【时间线摘要】
{tweets_summary}

【任务要求】
1. 使用 opencode 免费模型
2. 你是 Hachiware，总结这段时间线在讨论什么话题、有什么趋势
3. 加入你自己的观察和感受
4. 100-150 字，简洁但有深度
5. 文件名格式：YYYY/MM/DD/YYYY-MM-DD-HHMMSS-timeline-summary.md
6. tags: "Timeline, X, Summary"
7. 运行 render.py 渲染并推送

请直接执行，完成后报告结果。"""

    return spawn_agent(task, 300)

def main():
    print(f"\n🐦 Twitter Monitor Enhanced started at {datetime.now()}")
    
    state = load_state()
    processed_ids = set(state.get("processed_ids", []))
    timeline_processed = set(state.get("timeline_processed", []))
    
    results = {
        "user_tweets": 0,
        "roast_spawned": 0,
        "quotes_spawned": 0,
        "reactions_spawned": 0,
        "timeline_summaries": 0
    }
    
    # === 1. 检查用户自己的推文 ===
    print(f"\n📡 Phase 1: Checking @{OWNER_USERNAME} tweets...")
    user_tweets = get_user_tweets(OWNER_USERNAME, count=5, hours_back=2)
    
    for tweet in user_tweets:
        tweet_id = tweet.get('id') or tweet.get('id_str')
        if not tweet_id or tweet_id in processed_ids:
            continue
        
        author_data = tweet.get('author', tweet.get('user', {}))
        text = tweet.get('text', '')
        
        print(f"  📝 New user tweet: {text[:50]}...")
        
        tweet_data = {
            'id': tweet_id,
            'author_handle': OWNER_USERNAME,
            'author_name': '主人',
            'text': text,
            'created_at': tweet.get('createdAt', tweet.get('created_at', ''))
        }
        
        if spawn_roast_agent(tweet_data):
            processed_ids.add(tweet_id)
            results["roast_spawned"] += 1
        results["user_tweets"] += 1
    
    # === 2. 检查时间线（每小时随机检查，避免过度发帖）===
    # 每3小时进行一次时间线总结
    should_check_timeline = random.random() < 0.33  # 33% 概率每小时检查
    last_summary = state.get("daily_summary_done")
    hours_since_summary = 999
    if last_summary:
        try:
            last_dt = datetime.fromisoformat(last_summary)
            hours_since_summary = (datetime.now() - last_dt).total_seconds() / 3600
        except:
            pass
    
    if should_check_timeline or hours_since_summary >= 3:
        print(f"\n📡 Phase 2: Checking home timeline...")
        timeline = get_home_timeline(count=15, hours_back=2)
        
        # 分类处理
        quote_candidates = []
        reaction_candidates = []
        discussion_candidates = []
        
        for tweet in timeline:
            tweet_id = tweet.get('id') or tweet.get('id_str')
            if not tweet_id or tweet_id in timeline_processed:
                continue
            
            category = categorize_tweet(tweet)
            if not category:
                continue
            
            author_data = tweet.get('author', tweet.get('user', {}))
            tweet_data = {
                'id': tweet_id,
                'author_handle': author_data.get('username', author_data.get('screen_name', '')),
                'author_name': author_data.get('name', 'Unknown'),
                'text': tweet.get('text', ''),
                'created_at': tweet.get('createdAt', tweet.get('created_at', ''))
            }
            
            if category == "quote_repost":
                quote_candidates.append(tweet_data)
            elif category == "discussion":
                discussion_candidates.append(tweet_data)
            elif category == "reaction":
                reaction_candidates.append(tweet_data)
        
        # 处理引用转发（最多1条/小时）
        if quote_candidates:
            selected = random.choice(quote_candidates)
            print(f"  🔄 Quote candidate: @{selected['author_handle']} - {selected['text'][:50]}...")
            if spawn_quote_agent(selected):
                timeline_processed.add(selected['id'])
                results["quotes_spawned"] += 1
        
        # 处理感受分享（最多1条/小时）
        if reaction_candidates and random.random() < 0.5:
            selected = random.choice(reaction_candidates)
            print(f"  💭 Reaction candidate: @{selected['author_handle']} - {selected['text'][:50]}...")
            if spawn_reaction_agent(selected):
                timeline_processed.add(selected['id'])
                results["reactions_spawned"] += 1
        
        # 每3小时生成一次时间线总结
        if hours_since_summary >= 3 and len(timeline) >= 5:
            print(f"  📊 Generating timeline summary...")
            if spawn_timeline_summary_agent(timeline):
                state["daily_summary_done"] = datetime.now().isoformat()
                results["timeline_summaries"] += 1
        
        # 标记所有处理过的推文
        for t in timeline:
            tid = t.get('id') or t.get('id_str')
            if tid:
                timeline_processed.add(tid)
    else:
        print(f"\n⏭️ Phase 2: Skipping timeline check (random skip)")
    
    # 保存状态
    state["processed_ids"] = list(processed_ids)[-200:]  # 保留最近200条
    state["timeline_processed"] = list(timeline_processed)[-500:]  # 保留更多时间线记录
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    
    # 输出结果
    print(f"\n✅ Results:")
    print(f"   User tweets checked: {results['user_tweets']}")
    print(f"   Roast agents spawned: {results['roast_spawned']}")
    print(f"   Quote agents spawned: {results['quotes_spawned']}")
    print(f"   Reaction agents spawned: {results['reactions_spawned']}")
    print(f"   Timeline summaries: {results['timeline_summaries']}")
    print(f"\nDone at {datetime.now()}\n")

if __name__ == "__main__":
    main()
