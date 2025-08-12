#!/bin/bash

set -e

# Resolve script directory
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

echo "==== STARTING INSTALLATION ===="

# Fix ownership and permissions for project and Desktop (to avoid permission errors)
echo "🔧 Fixing ownership and permissions for project and Desktop..."
sudo chown -R pi:pi "$PROJECT_DIR"
sudo chown -R pi:pi /home/pi/Desktop
chmod -R u+rwX "$PROJECT_DIR"
chmod -R u+rwX /home/pi/Desktop

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

# Create autostart directory if needed
echo "📁 Ensuring LXDE autostart directory exists..."
mkdir -p "$LXDE_AUTOSTART_DIR"
sudo chown -R pi:pi "$LXDE_AUTOSTART_DIR"
chmod u+rwX "$LXDE_AUTOSTART_DIR"

# Write LXDE autostart file
echo "📝 Writing LXDE autostart file to $LXDE_AUTOSTART_FILE"
cat <<EOF > "$LXDE_AUTOSTART_FILE"
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xscreensaver -no-splash
@bash $START_SCRIPT
EOF
chmod u+rw "$LXDE_AUTOSTART_FILE"

# Make start script executable
echo "🚀 Making start.sh executable"
chmod +x "$START_SCRIPT"

# Create desktop shortcut
echo "🖥️ Creating desktop shortcut at $DESKTOP_FILE"
mkdir -p "/home/pi/Desktop"
sudo chown -R pi:pi /home/pi/Desktop
chmod u+rwX /home/pi/Desktop
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
sudo chown -R pi:pi "$PCMANFM_CONF_DIR"
chmod u+rwX "$PCMANFM_CONF_DIR"
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
chmod u+rw "$PCMANFM_CONF_FILE"

# Setup systemd user service
echo "📁 Ensuring systemd user directory exists..."
mkdir -p "$SYSTEMD_USER_DIR"
sudo chown -R pi:pi "$SYSTEMD_USER_DIR"
chmod u+rwX "$SYSTEMD_USER_DIR"

echo "📝 Writing systemd user service file to $SYSTEMD_SERVICE_FILE"
cat <<EOF > "$SYSTEMD_SERVICE_FILE"
[Unit]
Description=Start Chromium Kiosk Browser
After=network.target

[Service]
ExecStart=$START_SCRIPT
Restart=always
User=pi
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF
chmod u+rw "$SYSTEMD_SERVICE_FILE"

echo "🔄 Reloading systemd user daemon and enabling kiosk.service"
echo "Please run these commands as user 'pi' after login:"
echo " systemctl --user daemon-reload"
echo " systemctl --user enable kiosk.service"

echo "✅ Setup complete. Please reboot the Raspberry Pi to apply changes."
