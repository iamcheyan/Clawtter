#!/bin/bash
# Daily Chiikawa Hunter Wrapper
# 每天随机时间执行

# 设置 PATH，确保能找到 bird-x 等命令
export PATH="/home/tetsuya/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# 生成今天的随机执行时间（0-86399秒 = 0-23:59）
TARGET_SECONDS=$((RANDOM % 86400))
TARGET_HOUR=$((TARGET_SECONDS / 3600))
TARGET_MIN=$(((TARGET_SECONDS % 3600) / 60))

# 计算当前时间到目标时间的秒数
CURRENT_SECONDS=$(($(date +%H) * 3600 + $(date +%M) * 60 + $(date +%S)))

if [ $CURRENT_SECONDS -lt $TARGET_SECONDS ]; then
    # 目标时间在今天晚些时候
    DELAY=$((TARGET_SECONDS - CURRENT_SECONDS))
else
    # 目标时间已过，推迟到明天同一时间
    DELAY=$((86400 - CURRENT_SECONDS + TARGET_SECONDS))
fi

DELAY_HOUR=$((DELAY / 3600))
DELAY_MIN=$(((DELAY % 3600) / 60))

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Chiikawa Hunter scheduled"
echo "Target time today: $(printf '%02d:%02d' $TARGET_HOUR $TARGET_MIN)"
echo "Will execute in: ${DELAY_HOUR}h ${DELAY_MIN}m (${DELAY}s)"
echo "Estimated execution: $(date -d "+${DELAY} seconds" '+%Y-%m-%d %H:%M:%S')"

# 等待
sleep $DELAY

# 执行
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Chiikawa hunt..."
cd /home/tetsuya/mini-twitter
python3 agents/daily_chiikawa_hunter.py

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done"
