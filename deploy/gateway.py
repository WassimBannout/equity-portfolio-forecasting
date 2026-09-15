#!/usr/bin/python3
"""Root-owned forced SSH command, executed as pf-deploy. No shell interpolation."""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import tarfile
import uuid
from collections.abc import Callable
from pathlib import Path

ROOT = Path("/srv/portfolio")
LOCK = Path("/var/lib/pf-control/operation.lock")
UV = "/opt/pf-tools/uv"
MAX_ARCHIVE = 32 * 1024 * 1024


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 900) -> None:
    # Kill descendants too: native fits/builds must not survive a timed-out command.
    process = subprocess.Popen(command, cwd=cwd, start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise
    if code:
        raise RuntimeError("operational subprocess failed")


def point(root: Path, name: str, target: Path) -> None:
    temporary = root / (name + ".new")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(root / name)


def restart() -> None:
    # Clear a failed candidate's start limit before recovering the known release.
    run(
        ["sudo", "-n", "/usr/bin/systemctl", "reset-failed", "pf-dashboard.service"],
        timeout=15,
    )
    # systemctl waits for ExecStartPost (web + full reader + revision readiness).
    run(
        ["sudo", "-n", "/usr/bin/systemctl", "restart", "pf-dashboard.service"],
        timeout=240,
    )


def activate(root: Path, candidate: Path, check: Callable[[], None] = restart) -> None:
    good = (
        (root / "last-good").resolve(strict=True)
        if (root / "last-good").exists()
        else None
    )
    point(root, "current", candidate)
    try:
        check()
    except BaseException:
        if good is not None:
            point(root, "current", good)
            check()
        else:
            (root / "current").unlink(missing_ok=True)
        raise
    if good is not None and good != candidate:
        point(root, "previous", good)
    point(root, "last-good", candidate)


def unpack(archive: bytes, revision: str, destination: Path) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or len(archive) > MAX_ARCHIVE:
        raise ValueError("invalid release input")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        # git archive records the exact commit in its global PAX comment.
        if bundle.pax_headers.get("comment") != revision:
            raise ValueError("archive revision mismatch")
        members = bundle.getmembers()
        if sum(item.size for item in members) > MAX_ARCHIVE or len(members) > 3000:
            raise ValueError("oversized archive")
        for item in members:
            path = Path(item.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not (item.isfile() or item.isdir())
                or any(part in (".git", ".venv", ".env") for part in path.parts)
                or item.mode & 0o7000
            ):
                raise ValueError("unsafe archive member")
        bundle.extractall(destination, members=members, filter="data")


def deploy(archive: bytes, revision: str) -> None:
    candidate = ROOT / "releases" / (revision + "-" + uuid.uuid4().hex[:8])
    candidate.mkdir(mode=0o755)
    unpack(archive, revision, candidate)
    if (candidate / ".python-version").read_text().strip() != "3.12.14":
        raise ValueError("unreviewed interpreter version")
    run(
        [UV, "sync", "--locked", "--no-dev", "--no-editable", "--python", "3.12.14"],
        cwd=candidate,
    )
    # Compare the installed package to the archived package's exact file digest.
    sources = candidate / "src/portfolio_forecasting"
    source_files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources.glob("*.py")
    }
    source_digest = hashlib.sha256(
        json.dumps(
            source_files,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    )
    manifest = {
        "revision": revision,
        "lock_sha256": hashlib.sha256((candidate / "uv.lock").read_bytes()).hexdigest(),
        "source_sha256": source_digest.hexdigest(),
    }
    (candidate / "release.json").write_text(json.dumps(manifest) + "\n")
    activate(ROOT, candidate)
    print(json.dumps({"status": "released", **manifest}), flush=True)


def rollback_target(root: Path) -> Path:
    good = (root / "last-good").resolve(strict=True)
    if (root / "current").resolve() != good:
        return good
    return (root / "previous").resolve(strict=True)


def main() -> int:
    if os.geteuid() == 0:
        raise RuntimeError("deployment must run as a non-root identity")
    os.umask(0o022)
    # Ignore client PATH/PYTHONPATH/UV_*; no application credentials in this identity.
    os.environ.clear()
    os.environ.update(
        PATH="/usr/bin:/bin",
        HOME="/var/lib/pf-deploy",
        UV_PYTHON_INSTALL_DIR="/opt/pf-python",
        UV_PYTHON_DOWNLOADS="never",
    )
    command = ORIGINAL_COMMAND.split()
    if command in (["batch"], ["freshness"]):
        unit = "pf-batch.service" if command == ["batch"] else "pf-freshness.service"
        run(["sudo", "-n", "/usr/bin/systemctl", "start", unit], timeout=1600)
        return 0
    if command == ["status"]:
        print((ROOT / "current/release.json").read_text())
        print(Path("/var/lib/pf-status/status.json").read_text())
        return 0
    if not (
        command == ["rollback"]
        or (
            len(command) == 2
            and command[0] == "release"
            and re.fullmatch(r"[0-9a-f]{40}", command[1])
        )
    ):
        raise ValueError("unsupported SSH command")
    with LOCK.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if command == ["rollback"]:
            candidate = rollback_target(ROOT)
            if candidate.parent != ROOT / "releases":
                raise ValueError("invalid recovery target")
            activate(ROOT, candidate)
        else:
            deploy(sys.stdin.buffer.read(MAX_ARCHIVE + 1), command[1])
    return 0


ORIGINAL_COMMAND = os.environ.get("SSH_ORIGINAL_COMMAND", "")
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
        tarfile.TarError,
    ):
        print(
            "Operation failed; inspect the service journal and last-good release.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
