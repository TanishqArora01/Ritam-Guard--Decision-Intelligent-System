"""Basic pipeline contract checks for unified milestone-a structure.

These tests validate stage contract intent and folder layout without requiring
live services, so they are safe as smoke checks in CI.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_unified_folders_exist() -> None:
    assert (ROOT / "apps").is_dir()
    assert (ROOT / "services").is_dir()
    assert (ROOT / "platform").is_dir()
    assert (ROOT / "docs").is_dir()


def test_pipeline_services_exist() -> None:
    expected = [
        "txn-generator",
        "feature-engine",
        "risk-stage1",
        "risk-stage2",
        "decision-engine",
        "decision-sink",
        "gateway",
    ]
    for name in expected:
        assert (ROOT / "services" / name).is_dir(), f"Missing service: {name}"


def test_app_layers_exist() -> None:
    assert (ROOT / "apps" / "backend-api").is_dir()
    assert (ROOT / "apps" / "web-portal").is_dir()
