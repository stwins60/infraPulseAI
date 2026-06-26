#!/usr/bin/env python3
"""
InfraPulse AI — Linux Monitoring Agent
Collects system metrics, logs, and hardware info and sends to InfraPulse API.

Usage:
    infrapulse_agent.py --server-url https://your-domain --token <REGISTRATION_TOKEN>
    infrapulse_agent.py  (uses /etc/infrapulse/agent.conf if present)

Config file (~/.config/infrapulse/agent.conf or /etc/infrapulse/agent.conf):
    [agent]
    server_url = https://your-infrapulse-domain
    agent_token = <token-after-registration>
    interval = 30
    log_paths = /var/log/syslog,/var/log/auth.log
"""

import argparse
import configparser
import json
import logging
import os
import platform
import re
import socket
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("WARNING: psutil not installed. Install with: pip install psutil", file=sys.stderr)

# ── Constants ────────────────────────────────────────────────────────────────

VERSION = "1.0.0"
DEFAULT_INTERVAL = 30          # seconds between metric pushes
DEFAULT_LOG_INTERVAL = 60      # seconds between log batch pushes
DEFAULT_HEARTBEAT_INTERVAL = 60
DEFAULT_LOG_BATCH_SIZE = 100
CONFIG_PATHS = [
    "/etc/infrapulse/agent.conf",
    os.path.expanduser("~/.config/infrapulse/agent.conf"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("infrapulse-agent")


# ── Config ───────────────────────────────────────────────────────────────────

class AgentConfig:
    def __init__(self):
        self.server_url: str = ""
        self.agent_token: str = ""         # set after registration
        self.registration_token: str = ""  # one-time token for first registration
        self.interval: int = DEFAULT_INTERVAL
        self.log_interval: int = DEFAULT_LOG_INTERVAL
        self.heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL
        self.log_paths: list[str] = [
            "/var/log/syslog",
            "/var/log/auth.log",
            "/var/log/kern.log",
        ]
        self.log_batch_size: int = DEFAULT_LOG_BATCH_SIZE
        self.hostname_override: str = ""
        self.environment: str = "production"
        self.tags: list[str] = []

    def load_file(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        cp = configparser.ConfigParser()
        cp.read(path)
        sec = cp["agent"] if "agent" in cp else {}
        self.server_url = sec.get("server_url", self.server_url).rstrip("/")
        self.agent_token = sec.get("agent_token", self.agent_token)
        self.registration_token = sec.get("registration_token", self.registration_token)
        self.interval = int(sec.get("interval", self.interval))
        self.log_interval = int(sec.get("log_interval", self.log_interval))
        self.log_paths = [p.strip() for p in sec.get("log_paths", ",".join(self.log_paths)).split(",") if p.strip()]
        self.environment = sec.get("environment", self.environment)
        self.hostname_override = sec.get("hostname_override", self.hostname_override)
        tags_str = sec.get("tags", "")
        if tags_str:
            self.tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        log.info(f"Loaded config from {path}")
        return True

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cp = configparser.ConfigParser()
        cp["agent"] = {
            "server_url": self.server_url,
            "agent_token": self.agent_token,
            "interval": str(self.interval),
            "log_interval": str(self.log_interval),
            "log_paths": ",".join(self.log_paths),
            "environment": self.environment,
            "hostname_override": self.hostname_override,
            "tags": ",".join(self.tags),
        }
        with open(path, "w") as f:
            cp.write(f)
        log.info(f"Config saved to {path}")


# ── HTTP Client ───────────────────────────────────────────────────────────────

class APIClient:
    def __init__(self, server_url: str, agent_token: str = ""):
        self.server_url = server_url.rstrip("/")
        self.agent_token = agent_token

    def _request(self, method: str, path: str, data: Optional[dict] = None, timeout: int = 15) -> dict:
        url = f"{self.server_url}/api/v1{path}"
        body = json.dumps(data).encode() if data else None
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"InfraPulse-Agent/{VERSION}",
        }
        if self.agent_token:
            headers["X-Agent-Token"] = self.agent_token

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"HTTP {e.code}: {body[:200]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Connection error: {e.reason}")

    def post(self, path: str, data: dict) -> dict:
        return self._request("POST", path, data)

    def put(self, path: str, data: dict) -> dict:
        return self._request("PUT", path, data)


# ── System Info Collector ─────────────────────────────────────────────────────

class SystemInfo:
    @staticmethod
    def get_hostname(override: str = "") -> str:
        return override or socket.gethostname()

    @staticmethod
    def get_ip_addresses() -> list[str]:
        ips = []
        try:
            if HAS_PSUTIL:
                for iface, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                            ips.append(addr.address)
            else:
                hostname = socket.gethostname()
                ips = socket.gethostbyname_ex(hostname)[2]
                ips = [ip for ip in ips if not ip.startswith("127.")]
        except Exception:
            pass
        return ips or ["127.0.0.1"]

    @staticmethod
    def get_os_info() -> dict:
        info = {
            "os_type": platform.system(),
            "os_version": platform.version(),
            "kernel_version": platform.release(),
            "arch": platform.machine(),
        }
        # Try to read /etc/os-release for better distro info
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        info["os_version"] = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("ID="):
                        info["os_type"] = line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return info

    @staticmethod
    def get_cpu_info() -> dict:
        info = {}
        if HAS_PSUTIL:
            info["cpu_count_logical"] = psutil.cpu_count(logical=True)
            info["cpu_count_physical"] = psutil.cpu_count(logical=False)
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        info["cpu_model"] = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass
        return info

    @staticmethod
    def get_memory_info() -> dict:
        if not HAS_PSUTIL:
            return {}
        mem = psutil.virtual_memory()
        return {
            "total_bytes": mem.total,
            "available_bytes": mem.available,
        }


# ── Metrics Collector ─────────────────────────────────────────────────────────

class MetricsCollector:
    def __init__(self):
        self._last_net = None
        self._last_net_time = None
        self._last_disk_io = None
        self._last_disk_io_time = None

    def collect(self) -> list[dict]:
        if not HAS_PSUTIL:
            return []

        now = datetime.now(timezone.utc).isoformat()
        metrics = []

        def m(name, value, unit=""):
            metrics.append({"name": name, "value": round(float(value), 4), "unit": unit, "timestamp": now})

        # CPU
        try:
            cpu_pct = psutil.cpu_percent(interval=1)
            m("cpu_percent", cpu_pct, "%")
            load = psutil.getloadavg()
            m("load_average_1m", load[0])
            m("load_average_5m", load[1])
            m("load_average_15m", load[2])
        except Exception as e:
            log.debug(f"CPU metrics error: {e}")

        # Per-CPU (optional, up to 32 cores)
        try:
            per_cpu = psutil.cpu_percent(percpu=True)
            for i, pct in enumerate(per_cpu[:32]):
                m(f"cpu_core_{i}_percent", pct, "%")
        except Exception:
            pass

        # Memory
        try:
            mem = psutil.virtual_memory()
            m("memory_percent", mem.percent, "%")
            m("memory_used_bytes", mem.used, "bytes")
            m("memory_available_bytes", mem.available, "bytes")
            m("memory_total_bytes", mem.total, "bytes")
            swap = psutil.swap_memory()
            m("swap_percent", swap.percent, "%")
            m("swap_used_bytes", swap.used, "bytes")
        except Exception as e:
            log.debug(f"Memory metrics error: {e}")

        # Disk (root partition + others)
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    safe = part.mountpoint.replace("/", "_").strip("_") or "root"
                    m(f"disk_{safe}_percent", usage.percent, "%")
                    m(f"disk_{safe}_used_bytes", usage.used, "bytes")
                    m(f"disk_{safe}_total_bytes", usage.total, "bytes")
                    # Primary disk
                    if part.mountpoint == "/":
                        m("disk_percent", usage.percent, "%")
                        m("disk_used_bytes", usage.used, "bytes")
                        m("disk_total_bytes", usage.total, "bytes")
                except Exception:
                    pass
        except Exception as e:
            log.debug(f"Disk metrics error: {e}")

        # Disk I/O
        try:
            now_t = time.time()
            disk_io = psutil.disk_io_counters()
            if self._last_disk_io and self._last_disk_io_time:
                dt = now_t - self._last_disk_io_time
                if dt > 0:
                    m("disk_read_bytes_per_sec", (disk_io.read_bytes - self._last_disk_io.read_bytes) / dt, "bytes/s")
                    m("disk_write_bytes_per_sec", (disk_io.write_bytes - self._last_disk_io.write_bytes) / dt, "bytes/s")
            self._last_disk_io = disk_io
            self._last_disk_io_time = now_t
        except Exception:
            pass

        # Network
        try:
            now_t = time.time()
            net = psutil.net_io_counters()
            if self._last_net and self._last_net_time:
                dt = now_t - self._last_net_time
                if dt > 0:
                    m("net_bytes_recv", (net.bytes_recv - self._last_net.bytes_recv) / dt, "bytes/s")
                    m("net_bytes_sent", (net.bytes_sent - self._last_net.bytes_sent) / dt, "bytes/s")
                    m("net_packets_recv", (net.packets_recv - self._last_net.packets_recv) / dt, "pkt/s")
                    m("net_packets_sent", (net.packets_sent - self._last_net.packets_sent) / dt, "pkt/s")
            self._last_net = net
            self._last_net_time = now_t
        except Exception as e:
            log.debug(f"Net metrics error: {e}")

        # Process count
        try:
            m("process_count", len(psutil.pids()))
        except Exception:
            pass

        # Open file descriptors
        try:
            proc = psutil.Process()
            m("open_file_descriptors", proc.num_fds())
        except Exception:
            pass

        # Uptime
        try:
            uptime_sec = time.time() - psutil.boot_time()
            m("uptime_seconds", uptime_sec, "s")
        except Exception:
            pass

        return metrics


# ── Log Collector ─────────────────────────────────────────────────────────────

SYSLOG_PATTERN = re.compile(
    r'^(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)\s+(?P<host>\S+)\s+(?P<source>[^:]+):\s+(?P<message>.+)$'
)

LEVEL_KEYWORDS = {
    "critical": ["critical", "panic", "emerg", "alert"],
    "error": ["error", "err", "failed", "failure", "exception", "traceback"],
    "warning": ["warning", "warn", "deprecated"],
    "info": ["info", "notice", "started", "stopped", "connected"],
    "debug": ["debug", "trace"],
}


def detect_level(message: str) -> str:
    lower = message.lower()
    for level, keywords in LEVEL_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return level
    return "info"


class LogCollector:
    def __init__(self, log_paths: list[str], batch_size: int = 100):
        self.log_paths = log_paths
        self.batch_size = batch_size
        self._file_positions: dict[str, int] = {}

    def collect_new_lines(self) -> list[dict]:
        entries = []
        now = datetime.now(timezone.utc).isoformat()

        for path in self.log_paths:
            if not os.path.exists(path):
                continue
            try:
                current_size = os.path.getsize(path)
                last_pos = self._file_positions.get(path, current_size)  # start from end on first run

                if current_size < last_pos:
                    # File was rotated
                    last_pos = 0

                if current_size == last_pos:
                    continue

                with open(path, "r", errors="replace") as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    self._file_positions[path] = f.tell()

                source = os.path.basename(path)
                for line in new_lines[-self.batch_size:]:
                    line = line.rstrip()
                    if not line:
                        continue
                    level = detect_level(line)
                    entry = {
                        "timestamp": now,
                        "level": level,
                        "source": source,
                        "message": line[:2000],  # truncate very long lines
                    }
                    # Try to parse syslog format for better source
                    m = SYSLOG_PATTERN.match(line)
                    if m:
                        entry["source"] = m.group("source").split("[")[0].strip()
                        entry["message"] = m.group("message")[:2000]
                    entries.append(entry)

            except PermissionError:
                log.warning(f"Permission denied reading {path}")
            except Exception as e:
                log.debug(f"Error reading {path}: {e}")

        return entries


# ── Agent Main ────────────────────────────────────────────────────────────────

class InfraPulseAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.client = APIClient(config.server_url, config.agent_token)
        self.metrics_collector = MetricsCollector()
        self.log_collector = LogCollector(config.log_paths, config.log_batch_size)
        self.server_id: Optional[str] = None
        self._running = False

    def register(self) -> bool:
        """Register agent with server using registration token. Returns True on success."""
        hostname = SystemInfo.get_hostname(self.config.hostname_override)
        os_info = SystemInfo.get_os_info()
        cpu_info = SystemInfo.get_cpu_info()
        mem_info = SystemInfo.get_memory_info()

        payload = {
            "registration_token": self.config.registration_token,
            "hostname": hostname,
            "ip_addresses": SystemInfo.get_ip_addresses(),
            "os_type": os_info.get("os_type", "linux"),
            "os_version": os_info.get("os_version", ""),
            "kernel_version": os_info.get("kernel_version", ""),
            "arch": os_info.get("arch", ""),
            "cpu_model": cpu_info.get("cpu_model", ""),
            "cpu_count": cpu_info.get("cpu_count_logical", 0),
            "memory_total_bytes": mem_info.get("total_bytes", 0),
            "agent_version": VERSION,
            "environment": self.config.environment,
            "tags": self.config.tags,
        }

        log.info(f"Registering agent for hostname: {hostname}")
        try:
            result = self.client.post("/agent/register", payload)
            self.config.agent_token = result["agent_token"]
            self.server_id = result["server_id"]
            self.client.agent_token = self.config.agent_token
            log.info(f"Registration successful. Server ID: {self.server_id}")
            return True
        except Exception as e:
            log.error(f"Registration failed: {e}")
            return False

    def heartbeat(self):
        hostname = SystemInfo.get_hostname(self.config.hostname_override)
        uptime = None
        if HAS_PSUTIL:
            try:
                uptime = int(time.time() - psutil.boot_time())
            except Exception:
                pass
        try:
            self.client.post("/agent/heartbeat", {
                "hostname": hostname,
                "uptime_seconds": uptime,
                "agent_version": VERSION,
            })
            log.debug("Heartbeat sent")
        except Exception as e:
            log.warning(f"Heartbeat failed: {e}")

    def push_metrics(self):
        metrics = self.metrics_collector.collect()
        if not metrics:
            return
        try:
            self.client.post("/agent/metrics", {"metrics": metrics})
            log.debug(f"Pushed {len(metrics)} metrics")
        except Exception as e:
            log.warning(f"Metrics push failed: {e}")

    def push_logs(self):
        entries = self.log_collector.collect_new_lines()
        if not entries:
            return
        try:
            self.client.post("/agent/logs", {"entries": entries})
            log.debug(f"Pushed {len(entries)} log entries")
        except Exception as e:
            log.warning(f"Log push failed: {e}")

    def run(self):
        log.info(f"InfraPulse Agent v{VERSION} starting...")
        log.info(f"Server: {self.config.server_url}")

        if not self.config.agent_token and self.config.registration_token:
            if not self.register():
                log.error("Could not register with server. Exiting.")
                sys.exit(1)
            # Save updated config with agent_token
            for path in CONFIG_PATHS:
                if os.path.exists(path):
                    self.config.save(path)
                    break
            else:
                self.config.save(CONFIG_PATHS[0])
        elif not self.config.agent_token:
            log.error("No agent_token or registration_token configured. Exiting.")
            sys.exit(1)

        self._running = True
        last_heartbeat = 0
        last_log_push = 0
        last_metric_push = 0

        log.info(f"Agent running. Metrics every {self.config.interval}s, logs every {self.config.log_interval}s")

        while self._running:
            now = time.time()

            if now - last_heartbeat >= self.config.heartbeat_interval:
                self.heartbeat()
                last_heartbeat = now

            if now - last_metric_push >= self.config.interval:
                self.push_metrics()
                last_metric_push = now

            if now - last_log_push >= self.config.log_interval:
                self.push_logs()
                last_log_push = now

            time.sleep(1)

    def stop(self):
        self._running = False
        log.info("Agent stopping...")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=f"InfraPulse AI Agent v{VERSION}")
    parser.add_argument("--server-url", help="InfraPulse server URL (e.g. https://monitor.example.com)")
    parser.add_argument("--token", help="Registration token (one-time, from web UI)")
    parser.add_argument("--agent-token", help="Agent token (after registration)")
    parser.add_argument("--interval", type=int, help="Metrics push interval in seconds")
    parser.add_argument("--environment", help="Environment tag (production/staging/development)")
    parser.add_argument("--hostname", help="Override hostname")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--check", action="store_true", help="Run one metrics collection and exit (for testing)")
    args = parser.parse_args()

    if args.version:
        print(f"InfraPulse Agent v{VERSION}")
        sys.exit(0)

    config = AgentConfig()

    # Load config files
    config_path = args.config or next((p for p in CONFIG_PATHS if os.path.exists(p)), None)
    if config_path:
        config.load_file(config_path)

    # CLI overrides
    if args.server_url:
        config.server_url = args.server_url.rstrip("/")
    if args.token:
        config.registration_token = args.token
    if args.agent_token:
        config.agent_token = args.agent_token
    if args.interval:
        config.interval = args.interval
    if args.environment:
        config.environment = args.environment
    if args.hostname:
        config.hostname_override = args.hostname

    if not config.server_url:
        log.error("--server-url is required (or set server_url in config file)")
        sys.exit(1)

    if args.check:
        log.info("Running system check...")
        collector = MetricsCollector()
        metrics = collector.collect()
        print(json.dumps(metrics, indent=2))
        sys.exit(0)

    agent = InfraPulseAgent(config)

    import signal
    def handle_signal(signum, frame):
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    main()
