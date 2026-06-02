import shutil
import subprocess

import pytest
import yaml

pytestmark = [
    pytest.mark.helm,
    pytest.mark.skipif(shutil.which("helm") is None, reason="helm not available"),
]

CHART_PATH = "./charts/agentops"
DEV_VALUES = f"{CHART_PATH}/values.dev.yaml"


def _helm_template(*extra_args: str) -> list[dict]:
    """Render the chart and return parsed YAML documents."""

    result = subprocess.run(
        ["helm", "template", "agentops", CHART_PATH, "-f", DEV_VALUES, *extra_args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"helm template failed:\n{result.stderr}"
    return list(yaml.safe_load_all(result.stdout))


def test_helm_lint_passes() -> None:
    result = subprocess.run(
        ["helm", "lint", CHART_PATH, "-f", DEV_VALUES],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"helm lint failed:\n{result.stdout}\n{result.stderr}"


def test_dev_values_produce_nodeport_service() -> None:
    docs = _helm_template()
    services = [doc for doc in docs if doc and doc.get("kind") == "Service"]
    assert len(services) == 1
    service = services[0]
    assert service["spec"]["type"] == "NodePort"
    assert service["spec"]["ports"][0]["nodePort"] == 30080


def test_dev_values_set_image_pull_never() -> None:
    """imagePullPolicy must be Never in dev because the image is built in minikube."""

    docs = _helm_template()
    deployments = [doc for doc in docs if doc and doc.get("kind") == "Deployment"]
    assert len(deployments) == 1
    container = deployments[0]["spec"]["template"]["spec"]["containers"][0]
    assert container["imagePullPolicy"] == "Never"


def test_persistence_disabled_omits_pvc_and_mount() -> None:
    """Disabling persistence drops the PVC and volumeMounts entirely."""

    docs = _helm_template("--set", "audit.persistence.enabled=false")
    pvcs = [doc for doc in docs if doc and doc.get("kind") == "PersistentVolumeClaim"]
    assert pvcs == []
    deployments = [doc for doc in docs if doc and doc.get("kind") == "Deployment"]
    container = deployments[0]["spec"]["template"]["spec"]["containers"][0]
    assert "volumeMounts" not in container


def test_deployment_keeps_non_root_security_context() -> None:
    """Security context is not user-overridable; this is intentional."""

    docs = _helm_template()
    deployments = [doc for doc in docs if doc and doc.get("kind") == "Deployment"]
    security_context = deployments[0]["spec"]["template"]["spec"]["securityContext"]
    assert security_context["runAsNonRoot"] is True
    assert security_context["runAsUser"] == 1000
    assert security_context["fsGroup"] == 1000


def test_resources_match_dev_values() -> None:
    """values.dev.yaml resources are reflected in the deployment."""

    docs = _helm_template()
    deployments = [doc for doc in docs if doc and doc.get("kind") == "Deployment"]
    resources = deployments[0]["spec"]["template"]["spec"]["containers"][0]["resources"]
    assert resources["requests"]["memory"] == "256Mi"
    assert resources["limits"]["memory"] == "512Mi"
