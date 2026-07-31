from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_TESTS") != "1" or shutil.which("docker") is None,
    reason="Set RUN_DOCKER_TESTS=1 with Docker available to exercise non-root container user",
)
def test_container_runs_with_arbitrary_non_root_uid() -> None:
    image = "safedevops-foundation:test"
    subprocess.run(
        ["docker", "build", "-t", image, str(ROOT)],
        check=True,
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "12345:0",
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
            image,
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
