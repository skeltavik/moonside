"""Run from the repository root: python scripts/build_release.py v1.1.0 moonside.zip."""

import argparse
import json
import tomllib
import zipfile
from pathlib import Path


def main():
    """Validate release metadata before writing an integration-root HACS archive."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Exact release tag, such as v1.1.0")
    parser.add_argument("output", type=Path, help="Output ZIP archive path")
    args = parser.parse_args()

    integration = Path("custom_components/moonside")
    manifest = json.loads((integration / "manifest.json").read_text(encoding="utf-8"))
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    version = manifest["version"]
    project_version = project["project"]["version"]
    if version != project_version:
        parser.error(
            f"Manifest version {version} differs from project {project_version}"
        )
    if args.tag != f"v{version}":
        parser.error(f"Tag {args.tag!r} must match v{version}")

    cache_directories = {
        "__pycache__",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
    output = args.output.resolve()
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(integration.rglob("*")):
            relative = path.relative_to(integration)
            if (
                path.is_file()
                and not cache_directories.intersection(relative.parts)
                and path.suffix not in {".pyc", ".pyo"}
                and path.resolve() != output
            ):
                archive.write(path, relative.as_posix())


if __name__ == "__main__":
    main()
