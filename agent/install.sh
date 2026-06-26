#!/usr/bin/env bash
# InfraPulse AI — Agent Installer
# Usage: curl -sSL https://your-domain/agent/install.sh | bash -s -- --server-url https://your-domain --token TOKEN
# Or:    bash install.sh --server-url https://your-domain --token TOKEN [--environment production]

set -euo pipefail

AGENT_VERSION="1.0.0"
INSTALL_DIR="/opt/infrapulse"
CONFIG_DIR="/etc/infrapulse"
SERVICE_NAME="infrapulse-agent"
AGENT_USER="infrapulse"
PYTHON_MIN_VERSION="3.8"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()     { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; }
section() { echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

# ── Parse arguments ───────────────────────────────────────────────────────────
SERVER_URL=""
REGISTRATION_TOKEN=""
ENVIRONMENT="production"
HOSTNAME_OVERRIDE=""
TAGS=""
NO_SYSTEMD=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-url)       SERVER_URL="$2";           shift 2 ;;
    --token)            REGISTRATION_TOKEN="$2";   shift 2 ;;
    --environment)      ENVIRONMENT="$2";          shift 2 ;;
    --hostname)         HOSTNAME_OVERRIDE="$2";    shift 2 ;;
    --tags)             TAGS="$2";                 shift 2 ;;
    --no-systemd)       NO_SYSTEMD=true;           shift ;;
    -h|--help)
      echo "Usage: install.sh --server-url URL --token TOKEN [options]"
      echo ""
      echo "Options:"
      echo "  --server-url URL        InfraPulse server URL (required)"
      echo "  --token TOKEN           Registration token from web UI (required)"
      echo "  --environment ENV       Server environment tag (default: production)"
      echo "  --hostname NAME         Override hostname"
      echo "  --tags TAG1,TAG2        Comma-separated tags"
      echo "  --no-systemd            Don't install as systemd service"
      exit 0
      ;;
    *) error "Unknown argument: $1"; exit 1 ;;
  esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "$SERVER_URL" ]]; then
  error "Missing --server-url"
  echo "Usage: install.sh --server-url https://your-domain --token TOKEN"
  exit 1
fi
if [[ -z "$REGISTRATION_TOKEN" ]]; then
  error "Missing --token. Generate one from the web UI: Servers → + Add Server"
  exit 1
fi

SERVER_URL="${SERVER_URL%/}"  # strip trailing slash

# ── Check root ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  error "This script must be run as root (use sudo)"
  exit 1
fi

section "InfraPulse AI Agent Installer v${AGENT_VERSION}"
echo "  Server URL:   ${SERVER_URL}"
echo "  Environment:  ${ENVIRONMENT}"
echo "  Install dir:  ${INSTALL_DIR}"
echo ""

# ── Detect Python ─────────────────────────────────────────────────────────────
section "Checking Python"

PYTHON=""
for cmd in python3 python3.12 python3.11 python3.10 python3.9 python3.8; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    major="${ver%%.*}"
    minor="${ver##*.}"
    if [[ "$major" -ge 3 && "$minor" -ge 8 ]]; then
      PYTHON="$cmd"
      log "Found Python $ver: $PYTHON"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  warn "Python 3.8+ not found. Attempting to install..."
  if command -v apt-get &>/dev/null; then
    apt-get update -qq && apt-get install -y python3 python3-pip
    PYTHON="python3"
  elif command -v yum &>/dev/null; then
    yum install -y python3 python3-pip
    PYTHON="python3"
  elif command -v dnf &>/dev/null; then
    dnf install -y python3 python3-pip
    PYTHON="python3"
  else
    error "Could not install Python. Please install Python 3.8+ manually."
    exit 1
  fi
fi

# ── Install psutil ────────────────────────────────────────────────────────────
section "Installing dependencies"

install_psutil() {
  if $PYTHON -c "import psutil" &>/dev/null; then
    log "psutil already installed"
    return 0
  fi
  log "Installing psutil..."
  if command -v pip3 &>/dev/null; then
    pip3 install --quiet psutil
  elif $PYTHON -m pip &>/dev/null; then
    $PYTHON -m pip install --quiet psutil
  elif command -v apt-get &>/dev/null; then
    apt-get install -y python3-psutil
  elif command -v yum &>/dev/null; then
    yum install -y python3-psutil
  else
    warn "Could not install psutil automatically. Agent will have limited metrics."
    return 1
  fi
  log "psutil installed"
}

install_psutil || warn "Continuing without psutil (reduced metric collection)"

# ── Create user ───────────────────────────────────────────────────────────────
section "Creating service user"

if ! id "$AGENT_USER" &>/dev/null; then
  useradd --system --no-create-home --shell /bin/false "$AGENT_USER"
  log "Created user: ${AGENT_USER}"
else
  log "User ${AGENT_USER} already exists"
fi

# Add to adm group for log access
if getent group adm &>/dev/null; then
  usermod -aG adm "$AGENT_USER" || true
  log "Added ${AGENT_USER} to adm group (for log access)"
fi

# ── Install agent ─────────────────────────────────────────────────────────────
section "Installing agent"

mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"

# Download or copy agent script
SCRIPT_SOURCE="$(dirname "$(realpath "$0")")/infrapulse_agent.py"
if [[ -f "$SCRIPT_SOURCE" ]]; then
  cp "$SCRIPT_SOURCE" "${INSTALL_DIR}/infrapulse_agent.py"
  log "Copied agent from ${SCRIPT_SOURCE}"
else
  log "Downloading agent script from ${SERVER_URL}..."
  curl -sSL "${SERVER_URL}/agent/infrapulse_agent.py" -o "${INSTALL_DIR}/infrapulse_agent.py"
fi

chmod +x "${INSTALL_DIR}/infrapulse_agent.py"

# Create wrapper script
cat > /usr/local/bin/infrapulse-agent << EOF
#!/bin/bash
exec ${PYTHON} ${INSTALL_DIR}/infrapulse_agent.py "\$@"
EOF
chmod +x /usr/local/bin/infrapulse-agent

log "Agent installed to ${INSTALL_DIR}/infrapulse_agent.py"

# ── Write config ──────────────────────────────────────────────────────────────
section "Writing configuration"

# Detect available log paths
LOG_PATHS=""
for p in /var/log/syslog /var/log/messages /var/log/auth.log /var/log/secure /var/log/kern.log; do
  if [[ -f "$p" ]]; then
    LOG_PATHS="${LOG_PATHS},${p}"
  fi
done
LOG_PATHS="${LOG_PATHS#,}"  # remove leading comma

if [[ -z "$LOG_PATHS" ]]; then
  LOG_PATHS="/var/log/syslog"
fi

CURRENT_HOSTNAME=$(hostname -f 2>/dev/null || hostname)

cat > "${CONFIG_DIR}/agent.conf" << EOF
[agent]
server_url = ${SERVER_URL}
registration_token = ${REGISTRATION_TOKEN}
interval = 30
log_interval = 60
log_paths = ${LOG_PATHS}
environment = ${ENVIRONMENT}
hostname_override = ${HOSTNAME_OVERRIDE}
tags = ${TAGS}
EOF

chmod 600 "${CONFIG_DIR}/agent.conf"
chown root:root "${CONFIG_DIR}/agent.conf"

log "Config written to ${CONFIG_DIR}/agent.conf"

# ── Systemd service ───────────────────────────────────────────────────────────
if [[ "$NO_SYSTEMD" == "false" ]] && command -v systemctl &>/dev/null; then
  section "Installing systemd service"

  cat > "${SYSTEMD_SERVICE_PATH}" << EOF
[Unit]
Description=InfraPulse AI Monitoring Agent
Documentation=https://opencode.ai
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${AGENT_USER}
Group=${AGENT_USER}
ExecStart=${PYTHON} ${INSTALL_DIR}/infrapulse_agent.py --config ${CONFIG_DIR}/agent.conf
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=infrapulse-agent

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadOnlyPaths=/
ReadWritePaths=/etc/infrapulse
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
EOF

  # Allow agent user to read config
  chown -R "${AGENT_USER}:${AGENT_USER}" "${CONFIG_DIR}" || true

  # Allow agent user to read log files
  chmod 640 ${LOG_PATHS//,/ } 2>/dev/null || true
  chown root:adm ${LOG_PATHS//,/ } 2>/dev/null || true

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl start "${SERVICE_NAME}"

  sleep 2
  if systemctl is-active --quiet "${SERVICE_NAME}"; then
    log "Service started successfully!"
  else
    warn "Service may not have started. Check: journalctl -u ${SERVICE_NAME} -n 50"
  fi

else
  section "Skipping systemd (run manually)"
  echo ""
  echo "  To start the agent manually:"
  echo "  ${PYTHON} ${INSTALL_DIR}/infrapulse_agent.py --config ${CONFIG_DIR}/agent.conf"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
section "Installation Complete!"
echo ""
echo "  Agent:    ${INSTALL_DIR}/infrapulse_agent.py"
echo "  Config:   ${CONFIG_DIR}/agent.conf"
echo "  Service:  ${SERVICE_NAME}"
echo ""
echo "  Commands:"
echo "    systemctl status ${SERVICE_NAME}       # Check status"
echo "    journalctl -u ${SERVICE_NAME} -f       # Follow logs"
echo "    systemctl restart ${SERVICE_NAME}      # Restart agent"
echo "    systemctl stop ${SERVICE_NAME}         # Stop agent"
echo ""
echo "  The agent will appear in InfraPulse AI within 30-60 seconds."
echo ""
