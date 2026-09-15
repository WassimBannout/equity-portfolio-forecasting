"""Validate service/proxy configuration without provisioning the local host."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caddy", default="caddy")
    args = parser.parse_args()
    for shell, path in [
        ("bash", "scripts/remote.sh"),
        ("bash", "deploy/provision.sh"),
        ("sh", "deploy/pf-ready"),
    ]:
        subprocess.run([shell, "-n", path], cwd=ROOT, check=True)
    # systemd verify also checks executable existence. Supply inert executable
    # placeholders in an isolated root; no service is started or installed.
    with TemporaryDirectory(prefix="pf-unit-verify-") as directory:
        root = Path(directory)
        units = root / "etc/systemd/system"
        units.mkdir(parents=True)
        for pattern in ("*.service", "*.timer"):
            for unit in (ROOT / "deploy").glob(pattern):
                shutil.copy2(unit, units / unit.name)
        for name in (
            "sysinit.target",
            "basic.target",
            "shutdown.target",
            "network-online.target",
        ):
            (units / name).write_text(
                "[Unit]\nDescription=Static verification fixture\n"
            )
        for path in (
            "usr/bin/timeout",
            "usr/bin/flock",
            "usr/local/libexec/pf-ready",
            "srv/portfolio/current/.venv/bin/python",
        ):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/bin/sh\nexit 0\n")
            target.chmod(0o755)
        subprocess.run(
            [
                "systemd-analyze",
                "verify",
                "--man=no",
                "--root",
                directory,
                *[str(path) for path in sorted(units.glob("pf-*"))],
            ],
            check=True,
        )
    subprocess.run(
        [
            args.caddy,
            "adapt",
            "--config",
            str(ROOT / "deploy/Caddyfile"),
            "--adapter",
            "caddyfile",
            "--validate",
        ],
        env={**os.environ, "PF_DOMAIN": "portfolio.example.com"},
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print(
        "PASS: shell syntax; isolated systemd unit validation; "
        "Caddy HTTPS configuration"
    )


if __name__ == "__main__":
    main()
