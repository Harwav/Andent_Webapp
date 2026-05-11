"""Phase 0: Windows release workflow tests (TDD)."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "build-windows-exe.yml"


def _workflow_text() -> str:
    return WORKFLOW_FILE.read_text(encoding="utf-8")


def test_windows_release_workflow_publishes_to_public_repo() -> None:
    workflow = _workflow_text()

    assert "Harwav/Andent_Web_Release" in workflow
    assert "secrets.ANDENT_RELEASE_REPO_TOKEN" in workflow
    assert "Create GitHub Release in Public Repo" in workflow
    assert "gh release create $tagName" in workflow
    assert "gh release upload $tagName $exeFile --repo $repo" in workflow


def test_windows_release_workflow_keeps_hardening_checks() -> None:
    workflow = _workflow_text()

    assert "runs-on: windows-2022" in workflow
    assert 'python-version: "3.13.9"' in workflow
    assert 'cache: "pip"' in workflow
    assert "Import audit" in workflow
    assert "Focused packaging tests" in workflow
    assert "Verify build output" in workflow
    assert "EXE too small" in workflow
    assert "Smoke test EXE" in workflow
    assert "retention-days: 7" in workflow
    assert "Build summary" in workflow
