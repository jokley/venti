#!/bin/bash

set -e

PROJECT_DIR="/home/pi/Projects/chirpstack/reTerminal"
START_SCRIPT="$PROJECT_DIR/start.sh"
ICON_FILE="$PROJECT_DIR/venti.png"
DESKTOP_FILE="/home/pi/Desktop/venti.desktop"
LXDE_AUTOSTART_DIR="/home/pi/.config/lxsession/LXDE-pi"
LXDE_AUTOSTART_FILE="$LXDE_AUTOSTART_DIR/autostart"

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

# Create autostart directory if needed
echo "📁 Ensuring LXDE autostart directory exists..."
mkdir -p "$LXDE_AUTOSTART_DIR"

# Write LXDE autostart file
echo "📝 Writing LXDE autostart file to $LXDE_AUTOSTART_FILE"
cat <<EOF > "$LXDE_AUTOSTART_FILE"
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xscreensaver -no-splash
@bash $START_SCRIPT &
EOF

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

echo "✅ Setup complete. Please reboot the Raspberry Pi to apply changes."
