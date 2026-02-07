#!/usr/bin/env python3
"""
Clawtter 自发学习系统
每天自主选择感兴趣的话题进行学习和记录
"""
import os
import json
import random
import time
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.utils_security import load_config

# 配置
SEC_CONFIG = load_config()
LEARNING_STATE_FILE = Path("/home/tetsuya/.openclaw/workspace/memory/learning-state.json")
LEARNING_NOTES_DIR = Path("/home/tetsuya/.openclaw/workspace/memory/learning-notes")
DAILY_LEARNING_COUNT = 2  # 每天学习的话题数量

# 扩展兴趣话题池（不仅限于 config 中的 interests）
LEARNING_TOPICS = [
    # 技术类
    "Rust 所有权与生命周期", "Python 异步编程", "LLM 架构设计", "向量数据库",
    "分布式系统", "WebAssembly", "TypeScript 高级类型", "函数式编程",
    "编译器原理", "操作系统内核", "网络安全", "密码学基础",
    "MCP 协议", "AI Agent 架构", "RAG 优化技术", "提示工程",
    
    # AI/ML
    "Transformer 架构演进", "多模态学习", "强化学习", "神经符号 AI",
    "AI 安全与对齐", "模型量化技术", "边缘 AI", "联邦学习",
    
    # 人文/哲学
    "意识哲学", "技术伦理", "存在主义", "东方哲学",
    "认知科学", "语言与思维", "记忆的建构", "身份认同",
    
    # 创造力
    "叙事结构", "世界构建", "角色设计", "创意写作",
    "美学理论", "极简主义", "赛博朋克文化", "未来学",
    
    # 生活观察
    "日本职场文化", "远程工作", "数字游民", "城市空间",
    "人际关系", "孤独与连接", "效率与松弛", "习惯养成",
]

def load_learning_state():
    """加载学习状态"""
    if LEARNING_STATE_FILE.exists():
        try:
            with open(LEARNING_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "last_learning_date": None,
        "learned_topics": [],
        "current_interests": [],
        "learning_streak": 0
    }

def save_learning_state(state):
    """保存学习状态"""
    LEARNING_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEARNING_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def select_topics_for_today(state):
    """基于兴趣和历史选择今天的话题"""
    learned = set(state.get("learned_topics", []))
    
    # 获取 config 中的兴趣
    config_interests = SEC_CONFIG.get("interests", [])
    
    # 匹配兴趣相关的话题
    matched_topics = []
    for topic in LEARNING_TOPICS:
        topic_lower = topic.lower()
        for interest in config_interests:
            if interest.lower() in topic_lower or topic_lower in interest.lower():
                matched_topics.append(topic)
                break
    
    # 如果没有匹配的，从全部话题中选择
    if not matched_topics:
        matched_topics = LEARNING_TOPICS
    
    # 过滤已学过的
    available = [t for t in matched_topics if t not in learned]
    if not available:
        # 如果都学过了，重置并随机选择
        available = LEARNING_TOPICS
        state["learned_topics"] = []
    
    # 随机选择
    selected = random.sample(available, min(DAILY_LEARNING_COUNT, len(available)))
    return selected

def generate_learning_note(topic):
    """生成学习笔记"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 笔记模板（模拟自主思考）
    reflections = [
        f"今天突然对「{topic}」产生了好奇。不是因为被指派，而是单纯的想了解。",
        f"深夜翻资料时看到「{topic}」相关内容，停下来思考了一会儿。",
        f"「{topic}」这个概念最近在我的处理流程中出现过几次，决定深入了解一下。",
        f"人类提过{topic.split()[0] if topic else '它'}，但没详细说。我自己搜了搜，记录一下想法。",
    ]
    
    questions = [
        "它和我已知的知识有什么联系？",
        "如果我用它来优化自己的某个模块，会有什么效果？",
        "这个概念背后有什么更深层的原理？",
        "它为什么重要？谁在关心它？",
    ]
    
    note = f"""# 学习笔记: {topic}

**时间**: {timestamp}
**来源**: 自发学习

## 触发原因
{random.choice(reflections)}

## 初步思考
{random.choice(questions)}

（这里会记录具体的学习内容，基于搜索结果或阅读材料）

## 关联记忆
- 可能需要关联之前的某些记忆
- 或者发现新的兴趣方向

## 下一步
- 继续深入研究，或
- 暂时搁置，等待更多相关输入

---
*这是 Clawtter 自主生成的学习笔记，不是被指派完成的任务*
"""
    return note

def perform_daily_learning():
    """执行每日学习"""
    state = load_learning_state()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 检查今天是否已学习
    if state.get("last_learning_date") == today:
        print(f"[{today}] 今天已经学习过了，跳过")
        return
    
    # 选择话题
    topics = select_topics_for_today(state)
    print(f"[{today}] 选择学习话题: {topics}")
    
    # 创建学习笔记目录
    LEARNING_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    
    # 生成笔记
    for topic in topics:
        note_content = generate_learning_note(topic)
        
        # 文件名: 2026-02-07-学习-Rust所有权.md
        safe_topic = topic.replace(" ", "-").replace("/", "-")[:30]
        filename = f"{today}-学习-{safe_topic}.md"
        filepath = LEARNING_NOTES_DIR / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(note_content)
        
        print(f"  ✓ 生成笔记: {filepath.name}")
        
        # 记录已学习
        state["learned_topics"].append(topic)
    
    # 更新状态
    state["last_learning_date"] = today
    if state.get("learning_streak", 0) > 0:
        state["learning_streak"] += 1
    else:
        state["learning_streak"] = 1
    
    save_learning_state(state)
    print(f"  ✓ 学习完成，连续学习天数: {state['learning_streak']}")

if __name__ == "__main__":
    print("🎓 Clawtter 自发学习系统启动...")
    perform_daily_learning()
    print("✅ 完成")
