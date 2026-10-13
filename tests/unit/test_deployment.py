from pathlib import Path
import yaml

ROOT = Path(__file__).parents[2]

def test_optional_docker_deployment_configuration_is_hardened():
    compose = yaml.safe_load((ROOT / "deployment/docker/compose.yaml").read_text())
    service = compose["services"]["litman-core"]
    assert service["build"]["context"] == "../.."
    assert service["build"]["dockerfile"] == "deployment/docker/Dockerfile"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert ":/input:ro" in " ".join(service["volumes"])
    assert ":/output" in " ".join(service["volumes"])

def test_docker_image_enters_through_public_cli():
    dockerfile = (ROOT / "deployment/docker/Dockerfile").read_text().lower()
    assert 'entrypoint ["litman-core"]' in dockerfile
    assert "chromium" in dockerfile and "ripgrep" in dockerfile
    assert "bubblewrap" not in dockerfile and "bwrap" not in dockerfile

def test_docker_runtime_installs_builder_wheel_without_sources():
    dockerfile = (ROOT / "deployment/docker/Dockerfile").read_text().lower()
    runtime = dockerfile.split("from python:3.11-slim-bookworm", 2)[-1]
    assert "copy --from=builder /dist/litman_core-*.whl /tmp/" in dockerfile
    assert "pip install --no-cache-dir /tmp/litman_core-*.whl" in dockerfile
    assert "copy src" not in runtime
