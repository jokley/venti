#!/bin/bash
export DISPLAY=:0

GRAFANA_USERNAME="zotta"
GRAFANA_PASSWORD="zotta76@vent"

# # Load environment variables from .env file
# source ../venti.env

# # Ensure that the environment variables are set
# if [ -z "$GRAFANA_USERNAME" ] || [ -z "$GRAFANA_PASSWORD" ]; then
#   echo "Grafana username or password is not set in the .env file"
#   exit 1
# fi

# Encode username and password in Base64
AUTH=$(echo -n "$GRAFANA_USERNAME:$GRAFANA_PASSWORD" | base64)

# Wait until Grafana website is accessible
while true; do
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://172.16.238.19/)
    if [[ $RESPONSE -eq 200 ]]; then
        break
    elif [[ $RESPONSE -eq 302 ]]; then
        # Redirected to login page, authenticate with credentials
        chromium-browser --start-fullscreen --noerrdialogs --disable-gpu --user="$GRAFANA_USERNAME" --password="$GRAFANA_PASSWORD" http://172.16.238.19/login --display=:0 &
        exit
    else
        sleep 1
    fi
done

# Grafana dashboard is accessible, launch the browser in fullscreen mode
chromium-browser --start-fullscreen --noerrdialogs --disable-gpu http://172.16.238.19/ --display=:0 &