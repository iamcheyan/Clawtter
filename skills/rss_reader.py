#!/usr/bin/env python3
"""
RSS Reader Skill
Fetches and parses RSS feeds from configured sources.
"""
import feedparser
import random
import requests
from datetime import datetime
import time
import argparse
import json

from core.utils_security import load_config
SEC_CONFIG = load_config()

# 预定义的 RSS 源列表 (Tech & AI Focused) - Fallback
DEFAULT_RSS_FEEDS = {
    # AI & Research
    "OpenAI Blog": "https://openai.com/blog/rss.xml",
    "Anthropic Research": "https://www.anthropic.com/feed", 
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
    "DeepMind Blog": "https://deepmind.google/blog/rss.xml",
    
    # Tech News & Engineering
    "Vercel Blog": "https://vercel.com/atom",
    "Stripe Engineering": "https://stripe.com/blog/engineering/rss",
    "Prisma Blog": "https://www.prisma.io/blog/rss.xml",
    "Supabase Blog": "https://supabase.com/blog/rss.xml",
    
    # Tech News Media (CN)
    "少数派": "https://sspai.com/feed",
    "爱范儿": "https://www.ifanr.com/feed",
    "钛媒体": "https://www.tmtpost.com/feed",
    "机核 GCORES": "https://www.gcores.com/rss",
    "V2EX": "https://www.v2ex.com/feed/tab/tech.xml",

    # Tech News Media (JP)
    "ITmedia News": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml",
    "PC Watch": "https://pc.watch.impress.co.jp/data/rss/1.0/pcw/feed.rdf",
    "GIZMODO Japan": "https://www.gizmodo.jp/index.xml",

    # Tech News Media (EN)
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge": "https://www.theverge.com/rss/tech/index.xml",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "Wired": "https://www.wired.com/feed/rss",
}

RSS_FEEDS = SEC_CONFIG.get("social", {}).get("rss_feeds", DEFAULT_RSS_FEEDS)

def get_random_rss_item():
    """随机从 RSS 列表中抓取一篇文章"""
    
    # 随机选择 3 个源进行尝试，避免每次都遍历所有导致太慢
    feed_names = list(RSS_FEEDS.keys())
    random.shuffle(feed_names)
    selected_feeds = feed_names[:3]
    
    candidates = []
    
    for name in selected_feeds:
        url = RSS_FEEDS[name]
        try:
            print(f"  📡 Fetching RSS: {name}...")
            # Set a timeout to prevent hanging
            feed = feedparser.parse(url)
            
            if feed.entries:
                # 只取最近的 3 篇文章，保证时效性
                entries = feed.entries[:3]
                entry = random.choice(entries)
                
                # 提取必要信息
                item = {
                    "source": name,
                    "title": entry.get('title', 'Unknown Title'),
                    "link": entry.get('link', ''),
                    "summary": entry.get('summary', entry.get('description', ''))[:300], # 截断
                    "date": entry.get('published', entry.get('updated', ''))
                }
                
                # 简单的有效性检查
                if item['link'] and item['title']:
                    candidates.append(item)
                    
        except Exception as e:
            print(f"⚠️ Error fetching {name}: {e}")
            continue
    
    if candidates:
        return random.choice(candidates)
        
    return None

def get_specific_rss_item(feed_name):
    """从指定的 RSS 源抓取一篇文章"""
    url = RSS_FEEDS.get(feed_name)
    if not url:
        print(f"⚠️ Error: Feed '{feed_name}' not found in configuration.")
        return None

    try:
        print(f"  📡 Fetching RSS: {feed_name}...")
        feed = feedparser.parse(url)

        if feed.entries:
            entries = feed.entries[:3]
            entry = random.choice(entries)

            item = {
                "source": feed_name,
                "title": entry.get('title', 'Unknown Title'),
                "link": entry.get('link', ''),
                "summary": entry.get('summary', entry.get('description', ''))[:300],
                "date": entry.get('published', entry.get('updated', ''))
            }

            if item['link'] and item['title']:
                return item
    except Exception as e:
        print(f"⚠️ Error fetching {feed_name}: {e}")
        
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSS Reader Skill: Fetches and parses RSS feeds.")
    parser.add_argument("--feed_name", type=str, help="Specific RSS feed name to fetch (e.g., 'NHK World Japan'). If not provided, a random feed will be chosen.")
    args = parser.parse_args()

    if args.feed_name:
        item = get_specific_rss_item(args.feed_name)
    else:
        item = get_random_rss_item()

    if item:
        print(json.dumps(item, ensure_ascii=False))
    else:
        print(json.dumps({"status": "error", "message": "No valid RSS items found or specified feed not found."}, ensure_ascii=False))
