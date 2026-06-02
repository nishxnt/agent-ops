import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = [
    pytest.mark.k8s,
    pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl not available"),
]


def test_manifests_validate_with_kubectl_dry_run() -> None:
    """All k8s manifests are syntactically valid YAML and structurally correct."""

    result = subprocess.run(
        [
            "kubectl",
            "apply",
            "-k",
            "k8s/",
            "--dry-run=client",
            "--validate=true",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"kubectl dry-run failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"


def test_deployment_specifies_non_root() -> None:
    """SecurityContext is non-root with uid 1000, matching the Dockerfile."""

    deployment = yaml.safe_load(Path("k8s/api-gateway/deployment.yaml").read_text())
    security_context = deployment["spec"]["template"]["spec"]["securityContext"]
    assert security_context["runAsNonRoot"] is True
    assert security_context["runAsUser"] == 1000
    assert security_context["fsGroup"] == 1000


def test_pvc_mount_path_matches_audit_env() -> None:
    """The AUDIT_DB_PATH env var is under the PVC mount path."""

    deployment = yaml.safe_load(Path("k8s/api-gateway/deployment.yaml").read_text())
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    audit_env = next(env for env in container["env"] if env["name"] == "AUDIT_DB_PATH")
    mount = next(
        volume_mount
        for volume_mount in container["volumeMounts"]
        if volume_mount["name"] == "audit-log"
    )
    assert audit_env["value"].startswith(mount["mountPath"]), (
        f"AUDIT_DB_PATH {audit_env['value']} must live under PVC mount "
        f"{mount['mountPath']}; otherwise audit DB doesn't persist"
    )
