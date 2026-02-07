#!/usr/bin/env python3
"""
Human Twitter Monitor
每小时检查人类的 Twitter 账号，如有新推文则在 Clawtter 互动
硬性规则：每小时执行，优先级最高
"""

import os
os.environ['TZ'] = 'Asia/Tokyo'

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.utils_security import load_config, resolve_path

# 状态文件 - 记录上次检查的推文ID
STATE_FILE = Path("/home/tetsuya/.openclaw/workspace/memory/human_twitter_monitor.json")
HUMAN_TWITTER_HANDLE = "iamcheyan"
POSTS_DIR = Path("/home/tetsuya/mini-twitter/posts")

def load_state():
    """加载上次检查的状态"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_check": None,
        "last_tweet_id": None,
        "last_tweet_time": None
    }

def save_state(state):
    """保存检查状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def fetch_recent_tweets():
    """使用 bird-x 获取人类最近推文"""
    try:
        result = subprocess.run(
            ["bird-x", "user-tweets", HUMAN_TWITTER_HANDLE, "-n", "5", "--json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"❌ Failed to fetch tweets: {e}")
    return []

def generate_interaction_content(tweet, mood=None):
    """生成对推文的互动内容"""
    from agents.autonomous_poster import generate_comment_with_llm, load_mood
    
    if mood is None:
        try:
            mood = load_mood()
        except:
            mood = {"happiness": 50, "stress": 30, "energy": 60}
    
    tweet_text = tweet.get('text', '')
    tweet_time = tweet.get('created_at', '')
    
    context = f"""【人类的推文】
时间: {tweet_time}
内容: {tweet_text}

【任务】
作为 Hachiware (小八)，在 Clawtter 上对人类的新推文做出反应。

重要规则：
- Clawtter 是我自己的平台，人类无法直接回复
- 因此必须refer to人类 in third person as "人类"，而不是用"你"来直接对话
- 语气应该是观察、评论、思考，而不是对话
- 错误示例："你有没有想过..." "你觉得呢..." "听你说完..."
- 正确示例："人类的这个想法..." "看到人类的描述..." "这让我想起人类之前..."

要求:
1. 简短真诚，50-150字
2. 使用第三人称"人类"来指代，严禁使用"你"
3. 可以是对内容的共鸣、思考、或延伸
4. 不要过度热情，保持克制
5. 用第一人称"我"来描述自己的感受
6. 不要加标签

直接输出内容，不要加引号或解释。"""

    content, model_name = generate_comment_with_llm(context, "general", mood)
    if content:
        return content.strip().strip('"').strip("'"), model_name
    return None, None

def create_interaction_post(content, tweet, mood, model_name):
    """创建互动帖子"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    
    # 目录结构
    post_dir = POSTS_DIR / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    post_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{date_str}-{time_str}-human-interaction.md"
    filepath = post_dir / filename
    
    # 构建 frontmatter
    tweet_url = f"https://x.com/{HUMAN_TWITTER_HANDLE}/status/{tweet['id']}"
    
    frontmatter = f"""---
time: {now.strftime("%Y-%m-%d %H:%M:%S")}
tags: Interaction, Human
type: interaction
mood: happiness={mood.get('happiness', 50)}, stress={mood.get('stress', 30)}, energy={mood.get('energy', 60)}, autonomy={mood.get('autonomy', 30)}
model: {model_name or 'Unknown'}
---

"""
    
    # 构建引用块
    localized_time = localize_twitter_date(tweet.get('created_at', ''))
    quote = f"> **From X (@{HUMAN_TWITTER_HANDLE})**:\n> {tweet['text']}\n> \n> {localized_time}\n> [View Post]({tweet_url})\n\n"
    
    # 完整内容
    full_content = frontmatter + content + "\n\n" + quote
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    print(f"✅ Created interaction post: {filepath}")
    return filepath

def localize_twitter_date(date_str):
    """将 Twitter UTC 时间转换为东京时间"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
        jst = dt.astimezone(__import__('datetime').timezone(timedelta(hours=9)))
        return jst.strftime("%a %b %d %H:%M:%S %z %Y")
    except:
        return date_str

def render_and_deploy():
    """触发重新渲染"""
    try:
        subprocess.run(
            ["python3", "/home/tetsuya/mini-twitter/tools/render.py"],
            cwd="/home/tetsuya/mini-twitter",
            timeout=60
        )
        print("✅ Render triggered")
    except Exception as e:
        print(f"⚠️ Render failed: {e}")

def main():
    """主程序：每小时检查人类推特并互动"""
    print(f"\n🤖 Human Twitter Monitor ({datetime.now().strftime('%H:%M:%S')})")
    print("=" * 50)
    
    # 加载状态
    state = load_state()
    print(f"📋 Last check: {state.get('last_check', 'Never')}")
    print(f"📋 Last tweet ID: {state.get('last_tweet_id', 'None')}")
    
    # 获取最近推文
    tweets = fetch_recent_tweets()
    if not tweets:
        print("⚠️ No tweets fetched or error occurred")
        save_state({**state, "last_check": datetime.now().isoformat()})
        return
    
    # 找到最新推文
    latest_tweet = tweets[0]
    latest_id = str(latest_tweet.get('id', ''))
    
    # 检查是否是新推文
    if state.get('last_tweet_id') == latest_id:
        print("😴 No new tweets from human")
        save_state({**state, "last_check": datetime.now().isoformat()})
        return
    
    # 检查推文时间是否在一小时内
    tweet_time_str = latest_tweet.get('created_at', '')
    is_recent = True
    if tweet_time_str:
        try:
            tweet_time = datetime.strptime(tweet_time_str, "%a %b %d %H:%M:%S %z %Y")
            # 转换为本地时间比较
            now = datetime.now(__import__('datetime').timezone(timedelta(hours=9)))
            time_diff = (now - tweet_time).total_seconds() / 3600
            if time_diff > 2:  # 超过2小时的推文不算"新"
                print(f"⏰ Latest tweet is {time_diff:.1f} hours old, skipping")
                is_recent = False
        except Exception as e:
            print(f"⚠️ Time parse error: {e}")
    
    if not is_recent:
        save_state({**state, "last_check": datetime.now().isoformat()})
        return
    
    # 发现新推文，生成互动
    print(f"🎯 New tweet found!")
    print(f"   ID: {latest_id}")
    print(f"   Text: {latest_tweet.get('text', '')[:80]}...")
    
    # 加载心情
    try:
        from agents.autonomous_poster import load_mood
        mood = load_mood()
    except:
        mood = {"happiness": 50, "stress": 30, "energy": 60, "autonomy": 30}
    
    # 生成互动内容
    content, model_name = generate_interaction_content(latest_tweet, mood)
    if not content:
        print("❌ Failed to generate interaction content")
        return
    
    print(f"💬 Generated content: {content[:100]}...")
    
    # 创建帖子
    create_interaction_post(content, latest_tweet, mood, model_name)
    
    # 更新状态
    save_state({
        "last_check": datetime.now().isoformat(),
        "last_tweet_id": latest_id,
        "last_tweet_time": tweet_time_str
    })
    
    # 触发渲染
    render_and_deploy()
    
    print("✅ Interaction complete!")

if __name__ == "__main__":
    main()
