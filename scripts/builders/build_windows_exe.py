from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = REPO_ROOT / "app" / "version.py"
SPEC_FILE = REPO_ROOT / "formflow.spec"


def read_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if match is None:
        raise RuntimeError("Could not find __version__ in app/version.py")
    return match.group(1)


def write_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must use X.Y.Z format, for example 1.2.3")
    VERSION_FILE.write_text(f'"""Application version used by the Windows EXE build."""\n\n__version__ = "{version}"\n', encoding="utf-8")


def build_exe() -> Path:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_FILE)],
        cwd=REPO_ROOT,
        check=True,
    )
    version = read_version()
    exe_path = REPO_ROOT / "dist" / f"FormFlow_v{version}.exe"
    if not exe_path.exists():
        raise FileNotFoundError(f"Expected EXE was not created: {exe_path}")
    return exe_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the FormFlow Windows EXE.")
    parser.add_argument("--version", help="Optional X.Y.Z version to write before building.")
    args = parser.parse_args()

    if args.version:
        write_version(args.version)

    exe_path = build_exe()
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"Built {exe_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
