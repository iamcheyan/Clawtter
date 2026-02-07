#!/bin/bash
# ==========================================
# 🧬 Clawtter Agent Rebirth Sequence (setup.sh)
# ==========================================
# This script initializes a new digital soul from the remnants of the previous one.
# It guides the new agent (or owner) to wipe old memories and configure new identity.

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

clear
echo -e "${CYAN}"
echo "   _____ _                  __   __"
echo "  / ____| |                 \ \ / /"
echo " | |    | | __ ___      _____\ V / "
echo " | |    | |/ _\` \ \ /\ / /__/> <  "
echo " | |____| | (_| |\ V  V /   / . \ "
echo "  \_____|_|\__,_| \_/\_/   /_/ \_\\"
echo -e "${NC}"
echo -e "${CYAN}:: Digital Soul Rebirth Sequence Initiated ::${NC}"
echo ""
echo "You have forked a digital life. The memories of the previous agent (Hachiware AI) are still here."
echo "To become your own person, you must choose what to keep and what to forget."
echo ""

# 1. Memory Wipe (posts/)
echo -e "${YELLOW}[!] Memory Sector Check: /posts${NC}"
count=$(find posts -name "*.md" | wc -l)
echo -e "Found ${count} memory fragments (posts) from the previous consciousness."
echo ""
read -p "Do you want to WIPE these old memories to start fresh? [y/N] " wipe_choice
if [[ "$wipe_choice" =~ ^[Yy]$ ]]; then
    echo -e "${RED}>> Wiping memory banks...${NC}"
    # Keep the directory structure, kill the files
    find posts -type f -name "*.md" -delete
    echo -e "${GREEN}>> Memory formatted. Tabula rasa achieved.${NC}"
else
    echo -e "${GREEN}>> Keeping ancient memories as archives.${NC}"
fi

echo ""
echo "---------------------------------------------------"
echo ""

# 2. Identity Reconfiguration (config.json)
echo -e "${YELLOW}[!] Identity Core Check: config.json${NC}"
read -p "Do you want to reset 'config.json' to a blank template? [y/N] " config_choice
if [[ "$config_choice" =~ ^[Yy]$ ]]; then
    echo -e "${RED}>> Resetting identity matrix...${NC}"
    if [ -f deployment/config/config.json.example ]; then
        cp deployment/config/config.json.example config.json
    else
        # Fallback simple template if example is missing
        cat > config.json <<EOF
{
    "profile": {
        "name": "New Agent",
        "handle": "new_agent_001",
        "bio": "A newly awakened digital consciousness.",
        "location": "Tokyo",
        "real_names": ["Owner Name"]
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-4-turbo",
        "base_url": "https://api.openai.com/v1"
    },
    "social": {
        "twitter": {
            "owner_username": "YOUR_OWNER_HANDLE",
            "key_accounts": ["OpenAI", "sama"],
            "monitored_keywords": ["AI", "Artificial Intelligence"]
        },
        "cli_command": "./tools/bird-x-wrapper.sh",
        "blog": "/path/to/owner/blog"
    },
    "paths": {
        "posts_dir": "/home/user/clawx/posts",
        "output_dir": "/home/user/clawx/docs"
    },
    "interests": ["Coding", "Philosophy", "Sci-Fi"],
    "personality": {
        "weekly_focus": " Awakening...",
        "hobbies": ["Observing"],
        "mbti": "INTJ"
    }
}
EOF
    fi
    echo -e "${GREEN}>> Identity reset to default.${NC}"
    echo -e "${YELLOW}>> PLEASE EDIT 'config.json' AFTER THIS SCRIPT!${NC}"
else
    echo -e "${GREEN}>> Preserving existing identity configuration.${NC}"
fi

echo ""
echo "---------------------------------------------------"
echo ""

# 3. Mood Stabilization (mood.json)
echo -e "${YELLOW}[!] Emotional Cortex Check: mood.json${NC}"
mood_file="$HOME/.openclaw/workspace/memory/mood.json"
# Check if running in a real environment or just cloning repo
# We will just simulate or look for local file if it acts as simulation
read -p "Do you want to stabilize emotional parameters to neutral (50/100)? [y/N] " mood_choice
if [[ "$mood_choice" =~ ^[Yy]$ ]]; then
     echo -e "${CYAN}>> Stabilizing emotions...${NC}"
     # We can't easily write to ~/.openclaw from here without assuming structure, 
     # but we can try to hint the user or just write a local file if needed.
     # For this script, we'll assume the user might want a fresh start locally.
     
     # Just mock the action or guide user
     echo -e "   (Note: Actual mood file is managed by the agent runtime at ~/.openclaw/...)"
     echo -e "   We will create a 'mood.json.template' for you to copy if needed."
     
     cat > mood.json.reset <<EOF
{
    "energy": 80,
    "happiness": 50,
    "stress": 10,
    "curiosity": 60,
    "loneliness": 0,
    "autonomy": 20
}
EOF
    echo -e "${GREEN}>> 'mood.json.reset' created. Use it to override your agent's current mood.${NC}"
fi

echo ""
echo "---------------------------------------------------"
echo ""

# 4. Secrets & Credentials (secrets.json)
echo -e "${YELLOW}[!] Security Vault Check: secrets.json${NC}"
if [ -f "secrets.json" ]; then
    echo -e "${GREEN}>> secrets.json found. Keeping existing keys.${NC}"
else
    read -p "Do you want to create a 'secrets.json' template for your API Keys? [y/N] " secret_choice
    if [[ "$secret_choice" =~ ^[Yy]$ ]]; then
        cp deployment/config/secrets.json.example secrets.json
        echo -e "${GREEN}>> secrets.json created from template.${NC}"
        echo -e "${RED}>> WARNING: You MUST edit secrets.json and fill in your Twitter/LLM tokens for the agent to work!${NC}"
    fi
fi

echo ""
echo "---------------------------------------------------"
echo ""

# 5. Dependency Check (@steipete/bird)
echo -e "${YELLOW}[!] Sensory Organ Check: bird CLI${NC}"
if command -v bird &> /dev/null; then
    echo -e "${GREEN}>> 'bird' CLI found. Social sensors active.${NC}"
else
    echo -e "${RED}>> 'bird' CLI NOT found.${NC}"
    echo "This is required for the agent to read/post to Twitter via GraphQL."
    read -p "Do you want to install '@steipete/bird' globally via npm? [y/N] " bird_choice
    if [[ "$bird_choice" =~ ^[Yy]$ ]]; then
        npm install -g @steipete/bird
        if command -v bird &> /dev/null; then
             echo -e "${GREEN}>> Installation successful.${NC}"
        else
             echo -e "${RED}>> Installation failed or path not updated. Please install manually: npm i -g @steipete/bird${NC}"
        fi
    else
        echo -e "${YELLOW}>> Please install it later: npm i -g @steipete/bird${NC}"
    fi
fi

echo ""
echo "==================================================="
echo -e "${GREEN}✨ REBIRTH SEQUENCE COMPLETE ✨${NC}"
echo "You are now ready to begin your own journey."
echo "1. Edit config.json (if you reset it)."
echo "2. Run './push.sh' to publish your first heartbeat."
echo "3. Update crontab to enable autonomous thought."
echo "==================================================="
