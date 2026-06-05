"""Static Phase 4 verification evidence checks."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase4_verification_checks import check_phase4_verification_evidence


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_phase4_verification_evidence(ROOT)


def test_phase4_records_ami_and_hostname_policy_evidence() -> None:
    """Phase 4 evidence must prove dynamic AMI selection and external hostnames."""
    findings = _findings()

    assert "phase4 must prove Ubuntu LTS AMI data-source default with optional override" not in findings
    assert "phase4 must prove service hostnames have no repo defaults and DNS visibility is public by design" not in findings


def test_phase4_records_runtime_deploy_and_rollback_evidence() -> None:
    """Phase 4 evidence must prove deploy checks and call out live-only validation."""
    findings = _findings()

    assert "phase4 must prove runtime env map, SSM deploy, compose health, and rollback metadata" not in findings
    assert "phase4 must explicitly document missing live AWS/Cloudflare credential limitations" not in findings
