#!/usr/bin/env python3
"""Conservative, tenancy-wide inventory; rotate only our tagged volume backups.

Defaults to a read-only plan. --apply performs the rotation and briefly stops app writes.
Requires inspect/read access throughout the tenancy; missing permissions fail closed.
"""

import argparse
import fcntl
import json
import os
import signal
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TAG = {"application": "halekhoob"}


def cli(*arguments):
    command = [
        os.environ["OCI_CLI"],
        "--auth",
        os.environ.get("OCI_CLI_AUTH", "instance_principal"),
        "--region",
        os.environ["OCI_REGION"],
        "--output",
        "json",
        *arguments,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=3700)
    return json.loads(result.stdout or "{}")


def inventory():
    tenancy = os.environ["OCI_TENANCY_ID"]
    home = next(
        r
        for r in cli("iam", "region-subscription", "list", "--tenancy-id", tenancy)["data"]
        if r["is-home-region"]
    )
    if home["region-name"] != os.environ["OCI_REGION"]:
        raise RuntimeError("Refusing backups outside the home region.")
    compartments = [tenancy] + [
        c["id"]
        for c in cli(
            "iam",
            "compartment",
            "list",
            "--compartment-id",
            tenancy,
            "--compartment-id-in-subtree",
            "true",
            "--access-level",
            "ANY",
            "--all",
        )["data"]
        if c["lifecycle-state"] == "ACTIVE"
    ]
    backups = []
    for compartment in compartments:
        for kind in ("backup", "boot-volume-backup"):
            for backup in cli("bv", kind, "list", "--compartment-id", compartment, "--all")["data"]:
                if backup["lifecycle-state"] != "TERMINATED":
                    backups.append({**backup, "kind": kind})
    return backups


def rotation_plan(backups, data_volume, boot_volume):
    if any(b["lifecycle-state"] != "AVAILABLE" for b in backups):
        raise RuntimeError("A backup is in progress or unhealthy; no rotation performed.")
    data = sorted(
        [
            b
            for b in backups
            if b["kind"] == "backup"
            and b.get("volume-id") == data_volume
            and b.get("freeform-tags", {}).get("application") == TAG["application"]
        ],
        key=lambda b: b["time-created"],
    )
    boot = [
        b
        for b in backups
        if b["kind"] == "boot-volume-backup" and b.get("boot-volume-id") == boot_volume
    ]
    if len(boot) > 1 or len(backups) > 5:
        raise RuntimeError("Existing backups exceed the plan; review them manually.")
    removals = data[:-3] if len(data) >= 4 else []
    needed = 1 + (0 if boot else 1)
    if len(backups) - len(removals) + needed > 5:
        raise RuntimeError("Insufficient free backup slots. Unrelated backups will not be deleted.")
    return removals, not bool(boot)


def apply():
    backups = inventory()
    data_volume, boot_volume = os.environ["OCI_DATA_VOLUME_ID"], os.environ["OCI_BOOT_VOLUME_ID"]
    # Check source volume sizes too; a bigger volume would invalidate the free-tier plan.
    data = cli("bv", "volume", "get", "--volume-id", data_volume)["data"]
    boot = cli("bv", "boot-volume", "get", "--boot-volume-id", boot_volume)["data"]
    if data["size-in-gbs"] > 150 or boot["size-in-gbs"] > 50:
        raise RuntimeError("Source volumes exceed the agreed 150 + 50 GB allocation.")
    removals, create_boot = rotation_plan(backups, data_volume, boot_volume)
    print(
        json.dumps(
            {
                "existing_backups": len(backups),
                "rotate_managed_data_backups": len(removals),
                "create_boot_backup": create_boot,
                "create_data_backup": True,
            }
        )
    )
    if not ARGS.apply:
        return
    active = [
        unit
        for unit in ("motivation-worker", "motivation-web")
        if subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0
    ]
    try:
        if active:
            subprocess.run(["systemctl", "stop", *active], check=True, timeout=180)
        with sqlite3.connect("/srv/motivation/data/archive.sqlite3") as database:
            if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Database integrity check failed; not rotating backup.")
        subprocess.run(["sync"], check=True)
        for backup in removals:
            cli(
                "bv",
                "backup",
                "delete",
                "--volume-backup-id",
                backup["id"],
                "--force",
                "--wait-for-state",
                "TERMINATED",
                "--max-wait-seconds",
                "3600",
            )
        if create_boot:
            cli(
                "bv",
                "boot-volume-backup",
                "create",
                "--boot-volume-id",
                boot_volume,
                "--display-name",
                "halekhoob-boot",
                "--freeform-tags",
                json.dumps(TAG),
                "--type",
                "FULL",
                "--wait-for-state",
                "AVAILABLE",
                "--max-wait-seconds",
                "3600",
            )
        cli(
            "bv",
            "backup",
            "create",
            "--volume-id",
            data_volume,
            "--display-name",
            "halekhoob-daily",
            "--freeform-tags",
            json.dumps(TAG),
            "--type",
            "INCREMENTAL",
            "--wait-for-state",
            "AVAILABLE",
            "--max-wait-seconds",
            "3600",
        )
    finally:
        if active:
            subprocess.run(["systemctl", "start", *active], check=True, timeout=180)


if __name__ == "__main__":

    def interrupted(signum, frame):
        # Let apply()'s finally restart services even when systemd stops this job.
        raise InterruptedError("Backup interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    ARGS = parser.parse_args()
    with Path("/run/motivation-backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            apply()
            if ARGS.apply:
                Path("/srv/motivation/data/backup-status.json").write_text(
                    json.dumps({"success": True, "at": datetime.now(timezone.utc).isoformat()})
                )
        except Exception:
            if ARGS.apply:
                Path("/srv/motivation/data/backup-status.json").write_text(
                    json.dumps({"success": False, "at": datetime.now(timezone.utc).isoformat()})
                )
            raise
