#!/usr/bin/env python3
"""Run on the host as a timer; publish only coarse, non-secret monitoring data."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

DESTINATION = Path("/var/lib/halekhoob-monitor")


def cpu():
    parts = [int(n) for n in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
    return sum(parts), parts[3] + parts[4]


def main():
    first, idle = cpu()
    time.sleep(1)
    total, next_idle = cpu()
    memory = {
        line.split(":")[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
    }
    disk = shutil.disk_usage("/var/lib/docker")
    services = {}
    for name in ["web", "frontend", "worker", "db", "gateway"]:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{json .State}}", f"halekhoob-{name}-1"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            state = json.loads(result.stdout)
            services[name] = {
                "running": bool(state.get("Running")),
                "health": state.get("Health", {}).get("Status", "unknown"),
            }
        except (subprocess.SubprocessError, ValueError):
            services[name] = {"running": False, "health": "unavailable"}
    data = {
        "timestamp": time.time(),
        "cpu_percent": round(100 * (1 - (next_idle - idle) / max(1, total - first)), 1),
        "cpu_count": os.cpu_count(),
        "memory_total": memory["MemTotal"],
        "memory_used": memory["MemTotal"] - memory["MemAvailable"],
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_free": disk.free,
        "uptime_seconds": int(float(Path("/proc/uptime").read_text().split()[0])),
        "services": services,
    }
    DESTINATION.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = DESTINATION / "metrics.tmp"
    temporary.write_text(json.dumps(data))
    temporary.chmod(0o644)
    temporary.replace(DESTINATION / "metrics.json")


if __name__ == "__main__":
    main()
