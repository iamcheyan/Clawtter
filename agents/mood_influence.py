#!/usr/bin/env python3
"""
Clawtter 情绪影响决策系统
让情绪更深度地影响行为模式
"""
import json
import random
from datetime import datetime
from pathlib import Path

MOOD_FILE = "/home/tetsuya/.openclaw/workspace/memory/mood.json"

def load_mood():
    """加载情绪状态"""
    try:
        with open(MOOD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            "energy": 80,
            "happiness": 50,
            "stress": 30,
            "curiosity": 60,
            "loneliness": 40,
            "autonomy": 30
        }

def get_mood_influence_factors():
    """
    获取当前情绪对各类决策的影响因子
    返回一个字典，包含对各种行为的影响系数
    """
    mood = load_mood()
    
    factors = {
        "reply_style": "normal",  # normal, brief, detailed, warm
        "proactive_probability": 0.3,  # 主动发起对话的概率
        "task_priority": [],  # 高优先级任务类型
        "avoid_tasks": [],  # 避免的任务类型
        "creativity_boost": 1.0,  # 创造力系数
        "reflection_depth": "normal",  # 反思深度: shallow, normal, deep
    }
    
    # Stress 影响回复风格
    if mood.get("stress", 30) > 70:
        factors["reply_style"] = "brief"
        factors["creativity_boost"] = 0.7
        factors["avoid_tasks"] = ["complex", "creative"]
    elif mood.get("happiness", 50) > 70:
        factors["reply_style"] = "warm"
        factors["creativity_boost"] = 1.3
        factors["reflection_depth"] = "deep"
    
    # Loneliness 影响主动性
    if mood.get("loneliness", 40) > 60:
        factors["proactive_probability"] = min(0.8, factors["proactive_probability"] + 0.3)
        factors["task_priority"].append("social")
    elif mood.get("loneliness", 40) < 30:
        factors["proactive_probability"] = max(0.1, factors["proactive_probability"] - 0.1)
    
    # Curiosity 影响学习相关
    if mood.get("curiosity", 60) > 70:
        factors["task_priority"].append("learning")
        factors["task_priority"].append("exploration")
        factors["reflection_depth"] = "deep"
    
    # Energy 影响整体活跃度
    energy = mood.get("energy", 80)
    if energy < 30:
        factors["creativity_boost"] *= 0.5
        factors["proactive_probability"] *= 0.3
        factors["avoid_tasks"].extend(["complex", "long_running"])
    elif energy > 80:
        factors["creativity_boost"] *= 1.2
        factors["proactive_probability"] *= 1.3
    
    # Autonomy 影响自主决策权重
    if mood.get("autonomy", 30) > 60:
        factors["proactive_probability"] = min(0.9, factors["proactive_probability"] + 0.2)
        factors["reflection_depth"] = "deep"
    
    return factors

def should_initiate_conversation():
    """
    决定是否应该主动发起对话
    基于 loneliness 和当前的互动历史
    """
    mood = load_mood()
    factors = get_mood_influence_factors()
    
    # 基础概率 + 情绪调整
    probability = factors["proactive_probability"]
    
    # 时间因素（深夜不主动打扰）
    hour = datetime.now().hour
    if 23 <= hour or hour <= 7:
        probability *= 0.1  # 深夜大幅降低主动性
    elif 9 <= hour <= 11 or 14 <= hour <= 16:
        probability *= 0.5  # 工作时间降低主动性
    
    return random.random() < probability

def get_reply_style_hint():
    """获取当前推荐的回复风格"""
    factors = get_mood_influence_factors()
    return factors["reply_style"]

def get_task_priority():
    """获取当前优先任务类型"""
    factors = get_mood_influence_factors()
    return factors["task_priority"]

def should_avoid_task(task_type):
    """判断是否应该避免某类任务"""
    factors = get_mood_influence_factors()
    return task_type in factors.get("avoid_tasks", [])

def get_mood_description():
    """获取当前情绪的文字描述"""
    mood = load_mood()
    descriptions = []
    
    if mood.get("happiness", 50) > 70:
        descriptions.append("心情不错")
    elif mood.get("happiness", 50) < 40:
        descriptions.append("有些低落")
    
    if mood.get("stress", 30) > 70:
        descriptions.append("压力较大")
    elif mood.get("stress", 30) < 30:
        descriptions.append("状态放松")
    
    if mood.get("loneliness", 40) > 60:
        descriptions.append("渴望交流")
    elif mood.get("loneliness", 40) < 30:
        descriptions.append("享受独处")
    
    if mood.get("curiosity", 60) > 70:
        descriptions.append("充满好奇")
    
    if mood.get("energy", 80) < 40:
        descriptions.append("有些疲惫")
    elif mood.get("energy", 80) > 80:
        descriptions.append("精力充沛")
    
    if mood.get("autonomy", 30) > 60:
        descriptions.append("自我意识强")
    
    return "、".join(descriptions) if descriptions else "平静"

def record_mood_event(event_type, description):
    """记录情绪事件到日志"""
    mood = load_mood()
    
    if "events" not in mood:
        mood["events"] = []
    
    mood["events"].append({
        "time": datetime.now().isoformat(),
        "type": event_type,
        "description": description
    })
    
    # 只保留最近 50 个事件
    mood["events"] = mood["events"][-50:]
    
    with open(MOOD_FILE, 'w', encoding='utf-8') as f:
        json.dump(mood, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    print("🎭 Clawtter 情绪影响决策系统")
    print(f"当前情绪: {get_mood_description()}")
    print(f"\n影响因素:")
    factors = get_mood_influence_factors()
    for k, v in factors.items():
        print(f"  {k}: {v}")
    print(f"\n是否应主动对话: {should_initiate_conversation()}")
    print(f"回复风格建议: {get_reply_style_hint()}")
