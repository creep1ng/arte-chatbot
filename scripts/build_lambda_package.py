"""Build and scan the backend Lambda deployment package.

The script is safe for CI: it reads repository files, builds a zip artifact, and
checks the artifact for local secret files or obvious plaintext credentials. It
does not call AWS or GitHub APIs.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


DEFAULT_OUTPUT = Path("dist/lambda/backend.zip")
SOURCE_DIRECTORIES = ("backend", "rag")
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "tests",
}
EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo"}
SECRET_FILE_NAMES = {".env", ".env.deploy", "credentials"}
SECRET_FILE_PREFIXES = (".env.",)
PLAINTEXT_SECRET_MARKERS = (
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "OPENAI_API_KEY=sk-",
)


def build_package(
    project_root: Path,
    output_path: Path,
    *,
    include_dependencies: bool = True,
) -> None:
    """Build a Lambda zip package at ``output_path``.

    Args:
        project_root: Repository root.
        output_path: Destination zip path.
        include_dependencies: Whether to vendor dependencies via ``uv export``
            and ``pip install --target``.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with tempfile.TemporaryDirectory(prefix="arte-lambda-package-") as temp_dir:
        package_root = Path(temp_dir) / "package"
        package_root.mkdir()

        if include_dependencies:
            requirements_path = Path(temp_dir) / "requirements.txt"
            _run(
                [
                    "uv",
                    "export",
                    "--frozen",
                    "--no-dev",
                    "--format",
                    "requirements-txt",
                    "--output-file",
                    str(requirements_path),
                ],
                cwd=project_root,
            )
            _run(
                dependency_install_command(requirements_path, package_root),
                cwd=project_root,
            )

        for directory in SOURCE_DIRECTORIES:
            _copy_source_tree(project_root / directory, package_root / directory)

        _write_zip(package_root, output_path)

    findings = scan_package(output_path)
    if findings:
        for finding in findings:
            print(f"ERROR: {finding}", file=sys.stderr)
        raise SystemExit(1)


def scan_package(package_path: Path) -> list[str]:
    """Return package scan findings for forbidden files or secrets."""
    findings: list[str] = []
    if not package_path.exists():
        return [f"Lambda package does not exist: {package_path}"]

    with zipfile.ZipFile(package_path) as archive:
        for info in archive.infolist():
            normalized_name = info.filename.replace("\\", "/")
            path_parts = tuple(part for part in normalized_name.split("/") if part)
            file_name = path_parts[-1] if path_parts else normalized_name

            if _is_forbidden_secret_path(path_parts, file_name):
                findings.append(
                    f"package contains forbidden secret path: {normalized_name}"
                )
                continue

            if info.file_size > 1_000_000 or _looks_binary(file_name):
                continue

            try:
                content = archive.read(info).decode("utf-8")
            except UnicodeDecodeError:
                continue

            marker = _find_plaintext_secret_marker(content)
            if marker:
                findings.append(
                    f"package file {normalized_name} contains plaintext secret marker {marker!r}"
                )

    return findings


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest for ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_sha256(path: Path, expected_sha256: str) -> None:
    """Raise ``SystemExit`` if ``path`` does not match ``expected_sha256``."""
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise SystemExit(
            f"SHA-256 mismatch for {path}: expected {expected_sha256}, got {actual_sha256}"
        )


def dependency_install_command(
    requirements_path: Path, package_root: Path
) -> list[str]:
    """Return the dependency vendoring command used for Lambda packages.

    ``uv run python`` environments may not include the ``pip`` module. Calling
    ``uv pip install`` keeps local verification and CI package builds on the
    same toolchain without requiring ``python -m pip`` inside the venv.
    """
    return [
        "uv",
        "pip",
        "install",
        "--python",
        sys.executable,
        "--no-cache",
        "--requirement",
        str(requirements_path),
        "--target",
        str(package_root),
    ]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Lambda package output path.",
    )
    parser.add_argument(
        "--scan-only",
        type=Path,
        default=None,
        help="Scan an existing package instead of building a new one.",
    )
    parser.add_argument(
        "--assert-sha256",
        default="",
        help="Expected package SHA-256 digest.",
    )
    parser.add_argument(
        "--skip-dependencies",
        action="store_true",
        help="Build source-only zip for local script tests.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    project_root = Path.cwd()
    package_path = args.scan_only or args.output

    if args.scan_only is None:
        build_package(
            project_root,
            args.output,
            include_dependencies=not args.skip_dependencies,
        )

    findings = scan_package(package_path)
    if findings:
        for finding in findings:
            print(f"ERROR: {finding}", file=sys.stderr)
        raise SystemExit(1)

    if args.assert_sha256:
        assert_sha256(package_path, args.assert_sha256)

    digest = sha256_file(package_path)
    print(f"Lambda package ready: {package_path}")
    print(f"sha256={digest}")


def _copy_source_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Required source directory is missing: {source}")

    def ignore(_: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        for name in names:
            if name in EXCLUDED_DIR_NAMES:
                ignored.add(name)
            if name in SECRET_FILE_NAMES or name.startswith(SECRET_FILE_PREFIXES):
                ignored.add(name)
            if Path(name).suffix in EXCLUDED_FILE_SUFFIXES:
                ignored.add(name)
        return ignored

    shutil.copytree(source, destination, ignore=ignore)


def _write_zip(source_root: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_root.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, path.relative_to(source_root).as_posix())


def _is_forbidden_secret_path(path_parts: tuple[str, ...], file_name: str) -> bool:
    if ".aws" in path_parts:
        return True
    if file_name in SECRET_FILE_NAMES:
        return True
    return file_name.startswith(SECRET_FILE_PREFIXES)


def _find_plaintext_secret_marker(content: str) -> str:
    compact_content = content.replace(" ", "")
    for marker in PLAINTEXT_SECRET_MARKERS:
        marker_to_check = marker.replace(" ", "")
        if marker_to_check in compact_content:
            return marker
    return ""


def _looks_binary(file_name: str) -> bool:
    return Path(file_name).suffix.lower() in {
        ".a",
        ".bin",
        ".dist-info",
        ".jpg",
        ".png",
        ".so",
        ".whl",
    }


def _run(command: list[str], *, cwd: Path) -> None:
    env = os.environ.copy()
    env.setdefault("UV_NO_SYNC", "1")
    subprocess.run(command, cwd=cwd, env=env, check=True)


if __name__ == "__main__":
    main()
