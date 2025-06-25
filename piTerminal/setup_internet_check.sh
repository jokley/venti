#!/bin/bash

# Ensure script is run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root. Use sudo." 
   exit 1
fi

echo "Creating internet check script..."

# Step 1: Create the check script
cat << 'EOF' > /usr/local/bin/check_internet.sh
#!/bin/bash

# Define the address to ping
PING_ADDRESS="8.8.8.8"
PING_COUNT=4

# Define the USB device details
USB_ID="12d1:14db"

# Define the log file
LOG_FILE="/var/log/internet_check.log"

log_message() {
    echo "$(date): $1" >> "$LOG_FILE"
}

reboot_modem() {
    log_message "Rebooting Huawei E3371 modem by USB reset..."
    USB_BUS=$(lsusb | grep "$USB_ID" | awk '{print $2}')
    USB_DEV=$(lsusb | grep "$USB_ID" | awk '{print $4}' | sed 's/://')

    if [ -n "$USB_BUS" ] && [ -n "$USB_DEV" ]; then
        log_message "Found device on bus $USB_BUS, device $USB_DEV"

        echo "1-1" | sudo tee /sys/bus/usb/drivers/usb/unbind
        sleep 5
        echo "1-1" | sudo tee /sys/bus/usb/drivers/usb/bind
        sleep 10
    else
        log_message "Error: Unable to find the USB device"
    fi
}

restart_wireguard() {
    log_message "Restarting WireGuard service..."
    sudo systemctl restart wg-quick@wg0
}

if ping -c "$PING_COUNT" "$PING_ADDRESS" > /dev/null; then
    log_message "Internet connection is up."
else
    log_message "Internet connection is down."
    reboot_modem
    restart_wireguard
fi
EOF

# Step 2: Make it executable
chmod +x /usr/local/bin/check_internet.sh
echo "Script created and made executable."

# Step 3: Add to cronjob
echo "Installing cronjob..."
# Only add cronjob if it doesn't already exist
(crontab -l 2>/dev/null | grep -q "/usr/local/bin/check_internet.sh") || \
  (crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/check_internet.sh") | crontab -

# Step 4: Set up logrotate
echo "Setting up logrotate config..."

cat << 'EOF' > /etc/logrotate.d/internet_check
/var/log/internet_check.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 root root
    sharedscripts
    postrotate
        systemctl reload rsyslog > /dev/null 2>&1 || true
    endscript
}
EOF

# Step 5: Test logrotate config (optional)
echo "Testing logrotate config (dry run)..."
logrotate -d /etc/logrotate.d/internet_check

# Step 6: Force logrotate run (optional)
echo "Forcing logrotate..."
logrotate -f /etc/logrotate.d/internet_check

echo "✅ Setup complete!"
