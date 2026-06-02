import shutil
import subprocess
import time

import httpx
import pytest

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available"),
]

IMAGE_TAG = "agentops-api:pytest"
CONTAINER_NAME = "agentops-api-pytest"
HOST_PORT = 8002


@pytest.fixture(scope="module")
def built_image() -> str:
    result = subprocess.run(
        [
            "docker",
            "build",
            "-q",
            "-f",
            "docker/api.Dockerfile",
            "-t",
            IMAGE_TAG,
            ".",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"docker build failed: {result.stderr}")
    yield IMAGE_TAG


@pytest.fixture
def running_container(built_image: str) -> str:
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-p",
            f"{HOST_PORT}:8000",
            "-e",
            "AGENTOPS_MODE=mock",
            "-e",
            "BUDGET_TOKEN_LIMIT=100000",
            "--name",
            CONTAINER_NAME,
            built_image,
        ],
        check=True,
        timeout=30,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://localhost:{HOST_PORT}/healthz", timeout=2)
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        subprocess.run(["docker", "logs", CONTAINER_NAME])
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME])
        pytest.fail("Container did not become healthy within 30s")

    yield f"http://localhost:{HOST_PORT}"
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)


def test_container_healthz(running_container: str) -> None:
    response = httpx.get(f"{running_container}/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_container_readyz(running_container: str) -> None:
    response = httpx.get(f"{running_container}/readyz")
    assert response.status_code == 200


def test_container_runs_pipeline(running_container: str) -> None:
    response = httpx.post(
        f"{running_container}/run",
        json={"query": "What is FAISS?"},
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    deadline = time.time() + 30
    payload = None
    while time.time() < deadline:
        status_response = httpx.get(f"{running_container}/status/{run_id}")
        payload = status_response.json()
        if payload["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(1)

    assert payload is not None
    assert payload["status"] == "COMPLETED"
    assert payload["pipeline_status"] == "DONE"
    assert payload["decision"] == "PASS"
