import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gateway", ROOT / "deploy/gateway.py")
assert spec is not None and spec.loader is not None
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)
SHA = "a" * 40


def archive(member: tarfile.TarInfo | None = None, revision: str = SHA) -> bytes:
    data = io.BytesIO()
    with tarfile.open(
        fileobj=data,
        mode="w",
        format=tarfile.PAX_FORMAT,
        pax_headers={"comment": revision},
    ) as bundle:
        item = member or tarfile.TarInfo("README.md")
        bundle.addfile(item, io.BytesIO(b""))
    return data.getvalue()


def test_exact_archive_revision_and_safe_extraction(tmp_path: Path) -> None:
    gateway.unpack(archive(), SHA, tmp_path)
    assert (tmp_path / "README.md").is_file()
    with pytest.raises(ValueError, match="revision"):
        gateway.unpack(archive(revision="b" * 40), SHA, tmp_path)


@pytest.mark.parametrize("name", ["../outside", "/outside", ".venv/bin/python", ".env"])
def test_release_rejects_unsafe_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        gateway.unpack(archive(tarfile.TarInfo(name)), SHA, tmp_path)


def test_release_rejects_symlinks_and_oversize(tmp_path: Path) -> None:
    member = tarfile.TarInfo("link")
    member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
    with pytest.raises(ValueError, match="unsafe"):
        gateway.unpack(archive(member), SHA, tmp_path)
    with pytest.raises(ValueError, match="input"):
        gateway.unpack(b"x" * (gateway.MAX_ARCHIVE + 1), SHA, tmp_path)


def test_readiness_failure_restores_last_good_and_returns_failure(
    tmp_path: Path,
) -> None:
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    gateway.activate(tmp_path, good, lambda: None)
    seen = []

    def check() -> None:
        seen.append((tmp_path / "current").resolve())
        if seen[-1] == bad:
            raise RuntimeError("controlled readiness failure")

    with pytest.raises(RuntimeError):
        gateway.activate(tmp_path, bad, check)
    assert seen == [bad, good]
    assert (tmp_path / "last-good").resolve() == good
    assert (tmp_path / "current").resolve() == good


def test_success_and_manual_rollback_keep_previous(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    gateway.activate(tmp_path, first, lambda: None)
    gateway.activate(tmp_path, second, lambda: None)
    assert (tmp_path / "previous").resolve() == first
    gateway.activate(tmp_path, (tmp_path / "previous").resolve(), lambda: None)
    assert (tmp_path / "current").resolve() == first
    assert (tmp_path / "previous").resolve() == second


def test_failed_initial_release_does_not_create_last_good(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    with pytest.raises(RuntimeError):
        gateway.activate(
            tmp_path, candidate, lambda: (_ for _ in ()).throw(RuntimeError())
        )
    assert not (tmp_path / "current").is_symlink()
    assert not (tmp_path / "last-good").exists()


def test_timeout_terminates_process_group(tmp_path: Path) -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        gateway.run(["/bin/sleep", "10"], timeout=0)


def test_os_lock_excludes_a_second_process(tmp_path: Path) -> None:
    import fcntl

    lock_path = tmp_path / "operation.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(["flock", "--nonblock", str(lock_path), "true"])
        assert result.returncode == 1
    assert (
        subprocess.run(["flock", "--nonblock", str(lock_path), "true"]).returncode == 0
    )


def test_gateway_builds_new_locked_release_before_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "releases").mkdir()
    monkeypatch.setattr(gateway, "ROOT", tmp_path)

    def unpack(data: bytes, revision: str, candidate: Path) -> None:
        (candidate / ".python-version").write_text("3.12.14\n")
        (candidate / "uv.lock").write_text("lock fixture")
        (candidate / "src/portfolio_forecasting").mkdir(parents=True)
        (candidate / "src/portfolio_forecasting/__init__.py").write_text("")

    calls = []
    monkeypatch.setattr(gateway, "unpack", unpack)
    monkeypatch.setattr(gateway, "run", lambda command, **kwargs: calls.append(command))
    monkeypatch.setattr(
        gateway,
        "activate",
        lambda root, candidate: calls.append(["activate", str(candidate)]),
    )
    gateway.deploy(b"fixture", SHA)
    assert (
        "--locked" in calls[0]
        and "--no-dev" in calls[0]
        and "--no-editable" in calls[0]
    )
    manifest = json.loads((Path(calls[-1][1]) / "release.json").read_text())
    assert manifest["revision"] == SHA
    assert manifest["lock_sha256"] == hashlib.sha256(b"lock fixture").hexdigest()


def test_workflow_and_privilege_invariants() -> None:
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        value = path.read_text()
        assert "contents: read" in value
        for action in re.findall(r"uses: ([^\s]+)", value):
            assert action.startswith("./") or re.fullmatch(
                r"[^@]+@[0-9a-f]{40}", action
            )
    release = (ROOT / ".github/workflows/release.yml").read_text()
    assert "needs: quality" in release and "ref: ${{ github.sha }}" in release
    assert "PF_DATA_USE_APPROVED" in release and "git archive" in release
    daily = (ROOT / ".github/workflows/daily.yml").read_text()
    assert "cron: '0 9 * * *'" in daily
    for value in (release, daily):
        assert (
            "group: portfolio-production" in value
            and "cancel-in-progress: false" in value
        )
    for path in (ROOT / "deploy").glob("*.service"):
        value = path.read_text()
        assert "User=pf-" in value and "NoNewPrivileges=true" in value
        assert "ProtectSystem=strict" in value
    remote = (ROOT / "scripts/remote.sh").read_text()
    assert "StrictHostKeyChecking=yes" in remote and "ssh-keyscan" not in remote
    assert "pf-deploy@" in remote and "ForwardAgent=no" in remote


def test_remote_rejects_injected_host_without_executing_ssh() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/remote.sh"), "batch"],
        env={**os.environ, "SSH_HOST": "host; touch /tmp/unsafe"},
        capture_output=True,
    )
    assert result.returncode != 0


def test_interrupted_switch_recovers_last_good_not_older_previous(
    tmp_path: Path,
) -> None:
    first, second, interrupted = [
        tmp_path / name for name in ("first", "second", "interrupted")
    ]
    for directory in (first, second, interrupted):
        directory.mkdir()
    gateway.activate(tmp_path, first, lambda: None)
    gateway.activate(tmp_path, second, lambda: None)
    gateway.point(tmp_path, "current", interrupted)
    assert gateway.rollback_target(tmp_path) == second
    gateway.activate(tmp_path, gateway.rollback_target(tmp_path), lambda: None)
    assert (tmp_path / "current").resolve() == second
