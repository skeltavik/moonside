"""Exercise the release CLI and the archive installed by HACS."""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[1]
BUILDER = REPOSITORY / "scripts" / "build_release.py"


@pytest.fixture
def release_repository(tmp_path):
    """Use real integration assets with controlled release metadata."""
    integration = tmp_path / "custom_components" / "moonside"
    shutil.copytree(REPOSITORY / "custom_components" / "moonside", integration)
    manifest_path = integration / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = "1.1.0"
    manifest_path.write_text(json.dumps(manifest))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "moonside-home-assistant"\nversion = "1.1.0"\n'
    )
    for cache in ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"):
        cache_path = integration / cache
        cache_path.mkdir(exist_ok=True)
        (cache_path / "cached").write_text("not distributable")
    (integration / "stale.pyc").write_bytes(b"cached bytecode")
    (integration / "stale.pyo").write_bytes(b"cached bytecode")
    return tmp_path


def run_builder(repository, tag, archive):
    """Run the stdlib CLI without importing the integration."""
    return subprocess.run(
        [sys.executable, str(BUILDER), tag, str(archive)],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_archive_installs_at_integration_root(release_repository, tmp_path):
    """Catch missing assets, wrapper directories, and leaked caches."""
    archive = tmp_path / "moonside.zip"
    result = run_builder(release_repository, "v1.1.0", archive)
    assert result.returncode == 0, result.stderr
    install_path = tmp_path / "ha" / "custom_components" / "moonside"
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
        assert {
            "manifest.json",
            "__init__.py",
            "services.yaml",
            "strings.json",
            "brand/icon.png",
            "brand/icon@2x.png",
            "brand/logo.png",
            "brand/logo@2x.png",
        } <= names
        assert not any(
            part in {"custom_components", "moonside", "__pycache__"}
            or part.endswith("_cache")
            for name in names
            for part in Path(name).parts
        )
        assert not any(name.endswith((".pyc", ".pyo")) for name in names)
        package.extractall(install_path)
    assert (
        json.loads((install_path / "manifest.json").read_text())["version"] == "1.1.0"
    )
    assert (install_path / "brand" / "icon.png").read_bytes() == (
        release_repository / "custom_components" / "moonside" / "brand" / "icon.png"
    ).read_bytes()
    assert (install_path / "__init__.py").is_file()


def test_release_rejects_inconsistent_versions(release_repository, tmp_path):
    """A project/manifest mismatch must not overwrite an existing artifact."""
    (release_repository / "pyproject.toml").write_text(
        '[project]\nname = "moonside-home-assistant"\nversion = "1.0.0"\n'
    )
    archive = tmp_path / "moonside.zip"
    archive.write_bytes(b"existing artifact")
    result = run_builder(release_repository, "v1.1.0", archive)
    assert result.returncode != 0
    assert archive.read_bytes() == b"existing artifact"


@pytest.mark.parametrize("tag", ["v1.0.0", "1.1.0", "v1.1.0-rc1"])
def test_release_rejects_unmatched_tag(release_repository, tmp_path, tag):
    """Only the exact version tag may produce a release artifact."""
    archive = tmp_path / "moonside.zip"
    result = run_builder(release_repository, tag, archive)
    assert result.returncode != 0
    assert not archive.exists()


@pytest.mark.parametrize("case", ["delayed", "never", "mutable"])
def test_publication_waits_for_attestation_and_fails_closed(tmp_path, case):
    """GitHub's asynchronous attestation must not make a valid release fail."""
    workflow = yaml.safe_load(
        (REPOSITORY / ".github/workflows/release.yml").read_text()
    )
    command = next(
        step["run"]
        for step in workflow["jobs"]["release"]["steps"]
        if step["name"] == "Publish immutable release"
    )
    commands = tmp_path / "bin"
    commands.mkdir()
    gh = commands / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['release', 'edit']:\n"
        "    sys.exit(0)\n"
        "if args[0] == 'api':\n"
        "    print('false' if os.environ['RETRY_CASE'] == 'mutable' else 'true')\n"
        "    sys.exit(0)\n"
        "assert args[:2] == ['release', 'verify'], args\n"
        "counter = Path(os.environ['ATTEMPTS'])\n"
        "attempt = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(attempt))\n"
        "sys.exit(0 if os.environ['RETRY_CASE'] == 'delayed' and attempt >= 3 else 1)\n"
    )
    gh.chmod(0o755)
    sleep = commands / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    attempts = tmp_path / "attempts"
    result = subprocess.run(
        ["bash", "-e", "-c", command],
        env={
            **os.environ,
            "PATH": f"{commands}:{os.environ['PATH']}",
            "RELEASE_TAG": "v1.1.0",
            "GITHUB_REPOSITORY": "example/moonside",
            "RETRY_CASE": case,
            "ATTEMPTS": str(attempts),
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if case == "delayed":
        assert result.returncode == 0, result.stderr
        assert int(attempts.read_text()) == 3
    else:
        assert result.returncode != 0
        if case == "mutable":
            assert not attempts.exists()
        else:
            assert int(attempts.read_text()) > 1
