# Venti

Venti ist ein Docker-basierter Steuerungs- und Monitoring-Stack fuer eine
automatisierte Lueftungs- und Heizungssteuerung. Das System sammelt Sensorwerte,
schreibt sie nach InfluxDB, visualisiert sie in Grafana und steuert Luefter und
Heizung ueber MQTT.

Der Stack kann in zwei Varianten betrieben werden:

- LoRaWAN/ChirpStack: Sensorik und Relay-Kommandos laufen ueber ChirpStack,
  Mosquitto und Dragino LT-22222-L Downlinks.
- Panstamp/I2C: Sensordaten kommen lokal ueber einen Panstamp USB-Stick, Relays
  werden ueber I2C geschaltet.

## Komponenten

| Komponente | Aufgabe | Port |
| --- | --- | --- |
| `nginx` | Einstiegspunkt, Proxy auf Grafana, Backend und ChirpStack | `80` |
| `grafana` | Dashboards fuer Messwerte, Status und Steuerung | `3000` |
| `influxdb` | Zeitreihendatenbank fuer Sensor-, Steuer- und Statuswerte | `8086` |
| `backend` | Flask API, Regelung, Scheduler, Benachrichtigungen | `5000` |
| `mosquitto` | MQTT Broker fuer Downlinks und lokale Relay-Kommandos | `1883` |
| `watchdog` | Ueberwacht Backend, InfluxDB und optional Panstamp-Datenstrom | - |
| `chirpstack` | LoRaWAN Network Server fuer die ChirpStack-Variante | `8080` |
| `chirpstack-rest-api` | REST API fuer ChirpStack | `8090` |
| `panstamp-i2c` | Optionaler lokaler Panstamp- und I2C-Relay-Dienst | - |

Alle Container verwenden das Docker-Netzwerk `example-network` im Subnetz
`172.16.238.0/24`.

## Projektstruktur

```text
.
|-- docker-compose.yml                  # Voller Stack mit ChirpStack
|-- docker-compose-panstamp.yml         # Stack fuer Panstamp/I2C-Betrieb
|-- venti.env                           # Lokale Umgebungskonfiguration
|-- configuration/
|   |-- backend/                        # Flask Backend und Regelungslogik
|   |-- chirpstack/                     # ChirpStack Konfiguration und Decoder
|   |-- chirpstack-gateway-bridge/      # Gateway Bridge Konfiguration
|   |-- grafana/                        # Grafana Provisioning und Dashboards
|   |-- mosquitto/                      # MQTT Broker Konfiguration
|   |-- nginx/                          # Reverse Proxy Konfiguration
|   |-- panstamp-i2c/                   # Panstamp Serial Reader und I2C Relays
|   |-- postgresql/initdb/              # ChirpStack DB Initialisierung
|   `-- watchdog/                       # Docker Watchdog Service
`-- piTerminal/                         # Hilfsskripte fuer Raspberry Pi Terminal
```

## Backend

Das Backend ist eine Flask-Anwendung unter `configuration/backend`. Beim Start
werden MQTT, CORS, der Scheduler und die Controller initialisiert.

Wichtige Aufgaben:

- Lueftersteuerung mit den Modi `on`, `off` und `auto`
- Heizungssteuerung mit manueller und automatischer Laufzeit
- zyklische Regelung ueber APScheduler
- Persistenz von Modi, Parametern und Controller-Status in InfluxDB
- Versand von MQTT-Kommandos an Dragino oder Panstamp
- ntfy-Benachrichtigungen, Tageszusammenfassung und QR-Code-Routen
- Health- und Debug-Endpunkte fuer Betrieb und Watchdog

Die Regelung laeuft aktuell in diesen Intervallen:

- `venti_control`: alle 4 Minuten
- `heizung_control`: jede Minute

Die Controller-Dokumentation liegt zusaetzlich in
`configuration/backend/app/controller/venti/README.md`.

## Regelungslogik

Die Luefterentscheidung nutzt unter anderem:

- Betriebsmodus (`auto`, `on`, `off`)
- Temperatur, relative Feuchte, Trockenmasse und Saettigungsdefizit
- Stockaufbau-Zeit
- Ueberhitzungsschutz
- Intervalllueftung
- optionales Self-Learning fuer Trocknungseffizienz
- Batteriestatus, RSSI und Sensoralter fuer Systemzustand und Alerts

Die Heizung besitzt eigene Modi und Parameter. Der Heizungscontroller kann den
Luefter bei Bedarf mit ansteuern und beruecksichtigt eine Nachlaufzeit.

## API Endpunkte

Die wichtigsten Backend-Endpunkte:

| Methode | Pfad | Beschreibung |
| --- | --- | --- |
| `POST` | `/venti` | Lueftermodus setzen: `cmd`, `tm`, `stock` |
| `POST` | `/ventiParams` | Luefter-Regelparameter setzen |
| `GET` | `/controlValues` | Aktuelle Luefter-Steuerwerte lesen |
| `GET` | `/controlParamValues` | Aktuelle Luefterparameter lesen |
| `POST` | `/heizung` | Heizungsmodus setzen: `heizung_cmd`, `heizung_dauer`, `heizung_sdef_limit` |
| `POST` | `/heizungParams` | Heizungsparameter setzen, inkl. `heizung_sdef_hys` |
| `GET` | `/heizungValues` | Aktuelle Heizungs-Steuerwerte lesen |
| `GET` | `/heizungParamValues` | Aktuelle Heizungsparameter lesen |
| `GET` | `/debug` | Aktuellen Regelkontext ausgeben |
| `GET` | `/trace` | Regelentscheidung inklusive Trace ausgeben |
| `GET` | `/summary` | Tageszusammenfassung testweise senden |
| `GET` | `/healthz` | Backend-Liveness fuer Watchdog |
| `GET` | `/watchdog/status` | Influx- und Panstamp-Status fuer Watchdog |
| `POST` | `/ventiSystem` | Systemkommandos: `reboot`, `shutdown`, `refresh` |
| `GET` | `/qr/ntfy` | QR-Code fuer ntfy Topic |
| `GET` | `/qr/ios` | QR-Code zum iOS App Store |
| `GET` | `/qr/android` | QR-Code zum Android Play Store |

Ueber Nginx ist das Backend unter `/backend` erreichbar.

## Konfiguration

Die lokale Konfiguration wird aus `venti.env` geladen. Die Datei enthaelt
Zugangsdaten und sollte nicht mit echten Geheimnissen veroeffentlicht werden.

Relevante Variablen:

```text
DOCKER_INFLUXDB_INIT_MODE
DOCKER_INFLUXDB_INIT_USERNAME
DOCKER_INFLUXDB_INIT_PASSWORD
DOCKER_INFLUXDB_INIT_ORG
DOCKER_INFLUXDB_INIT_BUCKET
DOCKER_INFLUXDB_INIT_ADMIN_TOKEN
DOCKER_GRAFANA_INIT_USERNAME
DOCKER_GRAFANA_INIT_PASSWORD
GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH
APPLICATION_ID
DEVICE_ID
NTFY_BASE_URL
NTFY_TOPIC
```

Zusaetzlich unterstuetzt der Code optionale Variablen:

```text
PANSTAMP=true
PANSTAMP_MAX_SENSOR_AGE_SEC=300
FAN_DI1_CHECK_ENABLED=false
NODE_OUTDOOR00=<panstamp-node-id>
NODE_PROBE01=<panstamp-node-id>
NODE_PROBE02=<panstamp-node-id>
MQTT_BROKER_URL=172.16.238.15
MQTT_BROKER_PORT=1883
MQTT_KEEPALIVE=20
INFLUX_URL=http://172.16.238.16:8086
INFLUX_BUCKET=jokley_bucket
```

`FAN_DI1_CHECK_ENABLED=true` aktiviert die DI1-Pruefung der
Stern-Dreieck-Schuetzkombination. Standard ist `false`; bei `PANSTAMP=true`
bleibt die DI1-Pruefung deaktiviert. `FAN_DO1_CHECK_ENABLED` wird als
Rueckwaertskompatibilitaet ebenfalls gelesen, sollte aber durch
`FAN_DI1_CHECK_ENABLED` ersetzt werden.

## Starten

Voraussetzungen:

- Docker
- Docker Compose
- auf Raspberry Pi/Panstamp-Installationen Zugriff auf `/dev/ttyUSB0` und
  `/dev/i2c-1`

Voller Stack mit ChirpStack:

```bash
docker compose up -d --build
```

Panstamp/I2C-Variante:

```bash
docker compose -f docker-compose-panstamp.yml up -d --build
```

Logs ansehen:

```bash
docker compose logs -f backend
docker compose logs -f watchdog
docker compose -f docker-compose-panstamp.yml logs -f panstamp-i2c
```

Stack stoppen:

```bash
docker compose down
```

Bei der Panstamp-Variante:

```bash
docker compose -f docker-compose-panstamp.yml down
```

## Zugriff

Nach dem Start sind die Dienste typischerweise hier erreichbar:

- Grafana ueber Nginx: `http://localhost/`
- Grafana direkt: `http://localhost:3000/`
- Backend direkt: `http://localhost:5000/healthz`
- Backend ueber Nginx: `http://localhost/backend/healthz`
- InfluxDB: `http://localhost:8086/`
- ChirpStack: `http://localhost:8080/`
- ChirpStack REST API: `http://localhost:8090/`

## Datenfluss

### ChirpStack-Modus

1. LoRaWAN-Gateway sendet Sensordaten an ChirpStack.
2. ChirpStack publiziert MQTT Events ueber Mosquitto.
3. Decoder unter `configuration/chirpstack/decoder` bereiten Payloads auf.
4. Messwerte landen in InfluxDB.
5. Das Backend liest die aktuellen Werte aus InfluxDB.
6. Der Controller entscheidet ueber Luefter und Heizung.
7. Downlinks werden per MQTT an das Dragino Relay Device gesendet.

### Panstamp/I2C-Modus

1. `panstamp-i2c` liest Sensordaten von `/dev/ttyUSB0`.
2. `sensor_parser.py` zerlegt die Panstamp-Zeilen.
3. `main.py` berechnet Trockenmasse und Saettigungsdefizit.
4. `influx.py` schreibt ChirpStack-kompatible Measurements nach InfluxDB.
5. Das Backend sendet Relay-Kommandos auf `relay/control`.
6. `mqtt_handler.py` setzt die Relays ueber I2C und schreibt Relay-Statuswerte.

## Grafana

Grafana wird aus `configuration/grafana` provisioniert:

- Datenquelle: `configuration/grafana/provisioning/datasources/datasources.yaml`
- Dashboards: `configuration/grafana/dashboards/`
- Start-Dashboard ueber `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH`

Die Datenquelle verwendet InfluxDB v2 mit Flux und liest Organisation, Bucket
und Token aus `venti.env`.

## Watchdog

Der Watchdog ueberwacht:

- Backend-Liveness ueber `/healthz`
- InfluxDB-Verfuegbarkeit ueber `/watchdog/status`
- optional den Panstamp-Datenstrom ueber Sensoralter

Bei Fehlern startet er gezielt Container neu. Schutzmechanismen:

- Cooldown pro Container
- maximales Restart-Budget pro Stunde
- Retry-Logik fuer das Backend

Konfiguration erfolgt direkt in den Compose-Dateien ueber Variablen wie
`CHECK_INTERVAL_SEC`, `COOLDOWN_SEC` und `MAX_RESTARTS_PER_HOUR`.

## Persistenz

Docker Volumes:

- `influxdbv2`: InfluxDB Daten und Konfiguration
- `postgresqldata`: ChirpStack PostgreSQL Daten
- `redisdata`: ChirpStack Redis Daten

Beim Panstamp-Compose wird nur `influxdbv2` benoetigt.

## Hilfsskripte

- `delete_old_chirpstack_volumes.sh`: alte ChirpStack Volumes entfernen
- `migrate_chirpstack_to_venti.sh`: Migration/Anpassung bestehender Installation
- `piTerminal/setup_client.sh`: Bootstrap fuer neue Raspberry-Pi-Clients
- `piTerminal/install-docker.sh`: Docker Installation fuer Pi-Terminal
- `piTerminal/setup_wireguard.sh`: WireGuard Installation und Aktivierung
- `piTerminal/setup_internet_check.sh`: optionaler USB-Modem-Recovery-Timer
- `piTerminal/setup_rollout.sh`: optionaler Git-/Docker-Compose-Rollout-Timer
- `piTerminal/install_piterminal.sh`: Pi-Terminal- und Kiosk-Setup
- `piTerminal/start.sh`: robuster, Desktop-unabhaengiger Chromium-Kiosk-Start
- `piTerminal/start-kiosk-loop.sh`: startet den Kiosk nach einem Fehler erneut
- `piTerminal/venti.desktop`: manuell nutzbare Dashboard-Verknuepfung als Fallback

## Raspberry-Pi-Client einrichten

`piTerminal/setup_client.sh` richtet einen neuen Client modular ein. Docker,
WireGuard, Kiosk-Setup und der automatische Git-/Docker-Compose-Rollout werden
standardmaessig installiert, weil die aktuellen Venti-Clients Raspberry Pis mit
Display sind. Der USB-Modem-Recovery-Timer ist optional.

Die client-spezifische WireGuard-Datei enthaelt einen privaten Schluessel und
wird deshalb nicht committed. Fuer eine wiederholbare Installation kann sie auf
dem Client unter folgendem ignorierten Standardpfad abgelegt werden:

```text
piTerminal/client-configs/wg0.conf
```

Regulaerer Produktiv-Client mit Desktop-Kiosk, Rollout auf `main` und lokaler
`piTerminal/client-configs/wg0.conf`:

```bash
sudo ./piTerminal/setup_client.sh
```

QA-Client mit Rollout auf `qa`:

```bash
sudo ./piTerminal/setup_client.sh \
  --rollout-branch qa
```

Alternativ kann eine WireGuard-Konfiguration explizit uebergeben werden:

```bash
sudo ./piTerminal/setup_client.sh \
  --wireguard-config /root/client-configs/client-07-wg0.conf
```

Client mit Desktop-Kiosk, Rollout und Huawei-USB-Mobilfunkmodem:

```bash
sudo ./piTerminal/setup_client.sh \
  --wireguard-config /root/client-configs/client-08-wg0.conf \
  --usb-modem-recovery
```

Panstamp-Client mit passender Compose-Datei fuer den Rollout:

```bash
sudo ./piTerminal/setup_client.sh \
  --wireguard-config /root/client-configs/client-09-wg0.conf \
  --rollout-compose docker-compose-panstamp.yml
```

Eine vorhandene `/etc/wireguard/wg0.conf` wird nicht stillschweigend ersetzt.
Eine bewusste Aktualisierung erfolgt mit `--replace-wireguard-config`. Auf
bestehenden Clients mit bereits funktionierendem WireGuard kann dessen Schritt
mit `--skip-wireguard` uebersprungen werden. Falls Docker bereits separat
vorbereitet wurde, kann dessen Installation mit `--skip-docker` uebersprungen
werden. Fuer zukuenftige Headless-Clients kann das Kiosk-Setup mit `--no-kiosk`
ausgeschaltet werden. Der Rollout ist ebenfalls Standard und kann fuer Sonder-
oder Testfaelle mit `--no-rollout` deaktiviert werden. Eine vorhandene
`/etc/venti-update.conf` wird nur mit `--replace-rollout-config` ersetzt.

WireGuard wird als `wg-quick@wg0` aktiviert. Die wichtigsten Statusbefehle sind:

```bash
systemctl status docker
systemctl status wg-quick@wg0
```

Der optionale Internet-Check ist nur fuer Clients mit USB-Mobilfunkmodem
gedacht. Er laeuft als systemd-Timer, prueft alle fuenf Minuten die Verbindung,
ermittelt den USB-Sysfs-Pfad des Modems dynamisch und startet nach einem Fehler
WireGuard neu. Seine lokale Konfiguration liegt unter
`/etc/venti-internet-check.conf`. Status und Logs sind abrufbar mit:

```bash
systemctl list-timers venti-internet-check.timer
journalctl -u venti-internet-check.service --since today
```

Private WireGuard-Konfigurationen und lokale Provisionierungsdateien duerfen
nicht committed werden. Das Bootstrap-Script installiert den Rollout-Timer
standardmaessig; `piTerminal/setup_rollout.sh` bleibt fuer manuelle Wartung oder
nachtraegliche Konfigurationsaenderungen separat nutzbar.

## Automatischen Client-Rollout einrichten

Der Rollout wird bei `piTerminal/setup_client.sh` standardmaessig mitinstalliert.
`piTerminal/setup_rollout.sh` kann zusaetzlich direkt genutzt werden, um den
Rollout auf bestehenden Clients nachtraeglich einzurichten oder die lokale
Konfiguration bewusst zu ersetzen. Es installiert ein Laufzeitscript nach
`/usr/local/sbin/venti-update`, eine lokale Konfiguration unter
`/etc/venti-update.conf` sowie einen systemd-Timer. Das Script laeuft nicht
direkt aus dem Git-Checkout, damit es sich waehrend eines Updates nicht selbst
ersetzt.

QA-Client, der den Branch `qa` verfolgt:

```bash
sudo ./piTerminal/setup_rollout.sh \
  --branch qa \
  --compose docker-compose.yml
```

Produktiv-Client, der `main` verfolgt:

```bash
sudo ./piTerminal/setup_rollout.sh \
  --branch main \
  --compose docker-compose.yml
```

Panstamp-Client:

```bash
sudo ./piTerminal/setup_rollout.sh \
  --branch main \
  --compose docker-compose-panstamp.yml
```

Die lokale Konfiguration wird nur mit `--replace-config` ueberschrieben:

```bash
VENTI_DIR="/home/pi/Projects/venti"
DEPLOY_BRANCH="main"
COMPOSE_FILE="docker-compose.yml"
HEALTH_URL="http://127.0.0.1:5000/healthz"
HEALTH_RETRIES="12"
HEALTH_SLEEP_SEC="10"
COMPOSE_WAIT_TIMEOUT_SEC="180"
```

Der Timer prueft nach dem Boot und danach in regelmaessigen Abstaenden mit
zufaelliger Verzoegerung, ob `origin/$DEPLOY_BRANCH` einen neuen Commit hat. Bei
einem Update wird der Checkout hart auf den Remote-Stand gesetzt, die Compose-
Konfiguration validiert, Registry-Images werden geladen und der Stack mit Build,
`--remove-orphans` und `--wait` neu gestartet. Danach muss der Backend-
Health-Endpunkt erfolgreich antworten. Wenn Build, Start oder Health-Check
fehlschlagen, setzt das Script den vorherigen Commit zurueck und startet diesen
Stand erneut.

Wichtige Diagnosebefehle:

```bash
sudo -u pi /usr/local/sbin/venti-update
systemctl list-timers venti-update.timer
journalctl -u venti-update.service --since today
```

Der Rollout bricht ab, wenn versionierte Dateien lokale Aenderungen enthalten.
Client-spezifische Dateien wie `venti.env` und `/etc/venti-update.conf` bleiben
lokal und werden nicht aus Git ueberschrieben.

## Pi-Terminal-Kiosk einrichten

Das Kiosk-Setup startet Chromium erst nach dem grafischen Login des Benutzers
`pi`. Der Client muss deshalb so konfiguriert sein, dass sich `pi` automatisch
in eine grafische Sitzung einloggt. Das Setup erkennt aktuelle Raspberry-Pi-OS-
Installationen mit Wayland und `labwc`, aeltere LXDE/X11-Installationen und
verwendet fuer andere Desktop-Umgebungen XDG-Autostart als Fallback.

Einrichtung mit automatischer Erkennung:

```bash
sudo ./piTerminal/install_piterminal.sh --autostart auto
```

Bei Bedarf kann der Mechanismus explizit mit `--autostart labwc`,
`--autostart lxde` oder `--autostart xdg` ausgewaehlt werden. Das Setup
installiert immer nur einen aktiven Venti-Autostart und entfernt einen alten
systemweiten `kiosk.service`.

Die lokale Datei `/etc/venti-kiosk.conf` wird bei der ersten Einrichtung
erzeugt und bei spaeteren Setup-Aufrufen nicht ueberschrieben:

```bash
KIOSK_URL="http://127.0.0.1/?kiosk=1"
KIOSK_HEALTH_URL="http://127.0.0.1/"
KIOSK_WAIT_TIMEOUT_SEC="300"
```

Das Startskript wartet auf das Dashboard, erkennt `chromium` und
`chromium-browser`, verhindert doppelte Browserstarts und verwendet die vom
Desktop bereitgestellte X11- oder Wayland-Sitzung. Das Setup erzeugt ausserdem
eine Desktop-Verknuepfung aus der lokalen `KIOSK_URL`. Die versionierte Datei
`piTerminal/venti.desktop` bleibt als manuell nutzbarer Fallback erhalten. Ein
manueller Test muss aus einem Terminal innerhalb der grafischen Sitzung
erfolgen:

```bash
./piTerminal/start.sh
```

Nach der Installation sollte der Raspberry Pi mindestens zweimal neu gestartet
und der automatische Dashboard-Start geprueft werden. Je nach erkanntem Desktop
liegt der aktive Autostart in einer dieser Dateien:

```text
/home/pi/.config/labwc/autostart
/home/pi/.config/lxsession/LXDE-pi/autostart
/home/pi/.config/autostart/venti-kiosk.desktop
```

## Entwicklung

Backend-Abhaengigkeiten:

```bash
cd configuration/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Backend lokal starten:

```bash
cd configuration/backend
gunicorn -b 0.0.0.0:5000 wsgi:app
```

Vor lokalen Tests muessen InfluxDB und Mosquitto erreichbar sein oder passend
ueber Umgebungsvariablen konfiguriert werden.
