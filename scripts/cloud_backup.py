#!/usr/bin/env python3
"""Daily metadata / weekly full backups, with four successful copies of each kind."""

import argparse
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "destination", type=Path, help="Private host directory, outside the repository"
    )
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--server", action="store_true", help="Use the complete server Docker stack."
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = args.destination.resolve()
    if destination.is_relative_to(root):
        parser.error("Keep backups outside the source/deployment directory.")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    compose = (
        [str(root / "deploy/server.sh")]
        if args.server
        else ["docker", "compose", "-f", str(root / "deploy/compose.worker.yml")]
    )
    running = (
        "worker"
        in subprocess.check_output(
            [*compose, "ps", "--status", "running", "--services"], text=True
        ).splitlines()
    )
    kind = "full" if args.full else "metadata"
    name = f"{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}.tar"
    try:
        if running:
            subprocess.run([*compose, "stop", "worker"], check=True)
        command = [
            *compose,
            "run",
            "--rm",
            "--no-deps",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "DATA_DIR=/tmp/archive-maintenance",
            "-v",
            f"{destination}:/backups",
            "worker",
            "python",
            "manage.py",
            "export_portable",
            f"/backups/{name}",
        ]
        if not args.full:
            command.append("--metadata-only")
        subprocess.run(command, check=True)
        completed = destination / name
        if not completed.is_file():
            raise RuntimeError("No completed backup was created.")
        completed.chmod(0o600)
        backups = sorted(
            destination.glob(f"{kind}-*.tar"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        for path in backups[4:]:
            path.unlink()
    finally:
        if running:
            subprocess.run([*compose, "start", "worker"], check=True)


if __name__ == "__main__":
    main()
