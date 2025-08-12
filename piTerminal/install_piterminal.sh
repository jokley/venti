#!/bin/bash

set -e

echo "==== STARTING INSTALLATION ===="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$PROJECT_DIR/start.sh"
ICON_FILE="$PROJECT_DIR/venti.png"
BACKGROUND_IMAGE="$PROJECT_DIR/logo.jpg"
DESKTOP_FILE="/home/pi/Desktop/venti.desktop"
LXDE_AUTOSTART_DIR="/home/pi/.config/lxsession/LXDE-pi"
LXDE_AUTOSTART_FILE="$LXDE_AUTOSTART_DIR/autostart"
PCMANFM_CONF_DIR="/home/pi/.config/pcmanfm/LXDE-pi"
PCMANFM_CONF_FILE="$PCMANFM_CONF_DIR/desktop-items-0.conf"
SYSTEMD_USER_DIR="/home/pi/.config/systemd/user"
SYSTEMD_SERVICE_FILE="$SYSTEMD_USER_DIR/kiosk.service"

# Check required files
for f in "$START_SCRIPT" "$ICON_FILE" "$BACKGROUND_IMAGE"; do
  if [[ ! -f "$f" ]]; then
    echo "❌ ERROR: Required file not found: $f"
    exit 1
  fi
done

echo "🔧 Fixing ownership and permissions for project and Desktop..."
chown -R pi:pi /home/pi/Desktop "$PROJECT_DIR"
chmod +x "$START_SCRIPT"

echo "📁 Ensuring LXDE autostart directory exists..."
mkdir -p "$LXDE_AUTOSTART_DIR"

echo "📝 Writing LXDE autostart file to $LXDE_AUTOSTART_FILE"
cat > "$LXDE_AUTOSTART_FILE" <<EOF
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xscreensaver -no-splash
EOF

echo "🖥️ Creating desktop shortcut at $DESKTOP_FILE"
mkdir -p "/home/pi/Desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Link
Name=Heulüfter
Comment=Heulüfter Steuerung
Icon=$ICON_FILE
URL=http://172.16.238.19?kiosk=1
EOF
chmod +x "$DESKTOP_FILE"

echo "🖼️ Setting desktop background to $BACKGROUND_IMAGE"
mkdir -p "$PCMANFM_CONF_DIR"
if [[ -f "$PCMANFM_CONF_FILE" ]]; then
  sed -i "s|^wallpaper=.*|wallpaper=$BACKGROUND_IMAGE|" "$PCMANFM_CONF_FILE"
else
  cat > "$PCMANFM_CONF_FILE" <<EOF
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

echo "📁 Ensuring systemd user directory exists..."
mkdir -p "$SYSTEMD_USER_DIR"

echo "📁 Creating system-wide systemd service at /etc/systemd/system/kiosk.service..."

sudo tee /etc/systemd/system/kiosk.service > /dev/null <<EOF
[Unit]
Description=Start Chromium Kiosk Browser
After=graphical.target

[Service]
Type=simple
User=pi
ExecStart=$PROJECT_DIR/start.sh
Restart=on-failure
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Reloading systemd daemon and enabling kiosk.service..."
sudo systemctl daemon-reload
sudo systemctl enable kiosk.service

echo "✅ System-wide kiosk.service installed and enabled."

echo "✅ Setup complete. Please reboot the Raspberry Pi to apply changes."

