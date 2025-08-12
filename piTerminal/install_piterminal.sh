#!/bin/bash

set -e

# Resolve script directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$PROJECT_DIR/start.sh"
ICON_FILE="$PROJECT_DIR/venti.png"
BACKGROUND_IMAGE="$PROJECT_DIR/logo.jpg"
DESKTOP_FILE="/home/pi/Desktop/venti.desktop"

SYSTEMD_USER_DIR="/home/pi/.config/systemd/user"
SYSTEMD_SERVICE_FILE="$SYSTEMD_USER_DIR/kiosk.service"

PCMANFM_CONF_DIR="/home/pi/.config/pcmanfm/LXDE-pi"
PCMANFM_CONF_FILE="$PCMANFM_CONF_DIR/desktop-items-0.conf"

echo "==== STARTING INSTALLATION ===="

# Ensure required files exist
if [[ ! -f "$START_SCRIPT" ]]; then
    echo "❌ ERROR: $START_SCRIPT not found"
    exit 1
fi

if [[ ! -f "$ICON_FILE" ]]; then
    echo "❌ ERROR: $ICON_FILE not found"
    exit 1
fi

if [[ ! -f "$BACKGROUND_IMAGE" ]]; then
    echo "❌ ERROR: $BACKGROUND_IMAGE not found"
    exit 1
fi

# Make start script executable
echo "🚀 Making start.sh executable"
chmod +x "$START_SCRIPT"

# Create desktop shortcut
echo "🖥️ Creating desktop shortcut at $DESKTOP_FILE"
mkdir -p "/home/pi/Desktop"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Link
Name=Heulüfter
Comment=Heulüfter Steuerung
Icon=$ICON_FILE
URL=http://172.16.238.19?kiosk=1
EOF

chmod +x "$DESKTOP_FILE"

# Set the desktop background
echo "🖼️ Setting desktop background to $BACKGROUND_IMAGE"
mkdir -p "$PCMANFM_CONF_DIR"
if [[ -f "$PCMANFM_CONF_FILE" ]]; then
    sed -i "s|^wallpaper=.*|wallpaper=$BACKGROUND_IMAGE|" "$PCMANFM_CONF_FILE"
else
    cat <<EOF > "$PCMANFM_CONF_FILE"
[*]
wallpaper=$BACKGROUND_IMAGE
wallpaper_mode=stretch
desktop_bg=#000000
desktop_fg=#ffffff
desktop_shadow=false
desktop_font=Sans 10
show_wm_menu=false
sort=mtime;ascending;
space_between_icons=32
EOF
fi

# Create systemd user service directory
echo "📁 Ensuring systemd user directory exists..."
mkdir -p "$SYSTEMD_USER_DIR"

# Write systemd service file
echo "📝 Writing systemd user service file to $SYSTEMD_SERVICE_FILE"
cat <<EOF > "$SYSTEMD_SERVICE_FILE"
[Unit]
Description=Start Chromium Kiosk Browser
After=network.target

[Service]
ExecStart=$START_SCRIPT
Restart=on-failure
Environment=DISPLAY=:0
Environment=XDG_SESSION_TYPE=x11
# Add other environment variables here if needed

[Install]
WantedBy=default.target
EOF

# Reload systemd user daemon and enable service
echo "🔄 Reloading systemd user daemon and enabling kiosk.service"
systemctl --user daemon-reload
systemctl --user enable kiosk.service

echo "✅ Setup complete."
echo "👉 To start kiosk now: systemctl --user start kiosk.service"
echo "👉 The kiosk will auto-start on login after reboot."
