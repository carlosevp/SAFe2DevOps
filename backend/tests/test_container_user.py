from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "safedevops-foundation:test"


def _docker_available() -> bool:
    return os.environ.get("RUN_DOCKER_TESTS") == "1" and shutil.which("docker") is not None


@pytest.fixture(scope="module")
def built_image() -> str:
    if not _docker_available():
        pytest.skip("Set RUN_DOCKER_TESTS=1 with Docker available")
    subprocess.run(["docker", "build", "-t", IMAGE, str(ROOT)], check=True)
    return IMAGE


def _base_env() -> list[str]:
    return [
        "-e",
        "PORT=8000",
        "-e",
        "APP_ENV=production",
        "-e",
        "DATA_DIR=/data",
        "-e",
        "APP_SECRET_KEY=docker-test-app-secret-key-32b!",
        "-e",
        "DATA_ENCRYPTION_KEY=docker-test-data-encryption-key!",
        "-e",
        "ADMIN_PASSWORD_HASH=$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G2oQ.Y5zqK8K8K",
        "-e",
        "SQLITE_JOURNAL_MODE=DELETE",
    ]


@pytest.mark.skipif(not _docker_available(), reason="Set RUN_DOCKER_TESTS=1 with Docker available")
def test_container_runs_with_arbitrary_non_root_uid(built_image: str) -> None:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "12345:0",
            *_base_env(),
            built_image,
            "python",
            "-c",
            "import os; assert os.getuid()==12345; from pathlib import Path; "
            "p=Path('/data/db'); p.mkdir(parents=True, exist_ok=True); "
            "(p/'probe').write_text('ok'); print('ok')",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "ok" in result.stdout


@pytest.mark.skipif(not _docker_available(), reason="Set RUN_DOCKER_TESTS=1 with Docker available")
def test_container_persistence_and_graceful_shutdown(built_image: str, tmp_path: Path) -> None:
    volume = tmp_path / "data"
    volume.mkdir()
    name = f"safedevops-persist-{os.getpid()}"

    def run_once() -> None:
        cid = subprocess.check_output(
            [
                "docker",
                "create",
                "--name",
                name,
                "--user",
                "12345:0",
                "-v",
                f"{volume}:/data",
                *_base_env(),
                built_image,
            ],
            text=True,
        ).strip()
        try:
            subprocess.run(["docker", "start", cid], check=True)
            ready = False
            for _ in range(40):
                probe = subprocess.run(
                    [
                        "docker",
                        "exec",
                        cid,
                        "curl",
                        "-fsS",
                        "http://127.0.0.1:8000/api/health/ready",
                    ],
                    capture_output=True,
                    text=True,
                )
                if probe.returncode == 0:
                    ready = True
                    break
                time.sleep(2)
            assert ready, "readiness never became healthy"
            assert (volume / "db" / "safedevops.db").exists()
            export_dir = volume / "exports" / "probe"
            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "note.txt").write_text("persist-me", encoding="utf-8")
            subprocess.run(["docker", "kill", "--signal=SIGTERM", cid], check=False)
            for _ in range(30):
                state = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", cid],
                    capture_output=True,
                    text=True,
                )
                if state.stdout.strip() == "false":
                    break
                time.sleep(1)
        finally:
            subprocess.run(["docker", "rm", "-f", name], check=False)

    run_once()
    assert (volume / "exports" / "probe" / "note.txt").read_text(encoding="utf-8") == "persist-me"
    # Second start with pre-existing DB
    name2 = f"{name}-2"
    cid = subprocess.check_output(
        [
            "docker",
            "create",
            "--name",
            name2,
            "--user",
            "12345:0",
            "-v",
            f"{volume}:/data",
            *_base_env(),
            built_image,
        ],
        text=True,
    ).strip()
    try:
        subprocess.run(["docker", "start", cid], check=True)
        ready = False
        for _ in range(40):
            probe = subprocess.run(
                ["docker", "exec", cid, "curl", "-fsS", "http://127.0.0.1:8000/api/health/ready"],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                ready = True
                break
            time.sleep(2)
        assert ready
        assert (volume / "exports" / "probe" / "note.txt").exists()
    finally:
        subprocess.run(["docker", "rm", "-f", name2], check=False)
