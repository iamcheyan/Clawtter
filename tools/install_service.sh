#!/bin/bash
# =================================================
# Install Clawtter Suite as Systemd User Services
# =================================================
# Installs:
# - clawx-server.service (Preview Server)
# - clawx-bot.timer + .service (Autonomous Poster)
# - clawx-monitor.timer + .service (Model Health Check)

TARGET_DIR="$HOME/.config/systemd/user"
mkdir -p "$TARGET_DIR"

install_unit() {
    local NAME=$1
    local SOURCE="$(pwd)/deployment/systemd/$NAME"
    local TARGET="$TARGET_DIR/$NAME"
    
    echo "🔧 Installing $NAME..."
    if [ ! -f "$SOURCE" ]; then
        echo "❌ Source file not found: $SOURCE"
        return
    fi
    ln -sf "$SOURCE" "$TARGET"
    echo ">> Linked."
}

# 1. Server (Daemon)
install_unit "clawtter-server.service"

# 2. Bot (Timer + Service)
install_unit "clawtter-bot.service"
install_unit "clawtter-bot.timer"

# 3. Monitor (Timer + Service)
install_unit "clawtter-monitor.service"
install_unit "clawtter-monitor.timer"

# Reload
echo "🔄 Reloading systemctl user daemon..."
systemctl --user daemon-reload

# Enable and Start
echo "🚀 Enabling and Starting services..."
systemctl --user enable --now clawtter-server.service
systemctl --user enable --now clawtter-bot.timer
systemctl --user enable --now clawtter-monitor.timer

echo ""
echo "✅ Clawtter System Installed:"
echo "---------------------------------------------------"
systemctl --user status clawtter-server.service clawtter-bot.timer clawtter-monitor.timer --lines=0 --no-pager
echo "---------------------------------------------------"
echo "Log commands:"
echo "  Server: journalctl --user -u clawtter-server -f"
echo "  Bot:    journalctl --user -u clawtter-bot -f"
echo "  Monitor: journalctl --user -u clawtter-monitor -f"
