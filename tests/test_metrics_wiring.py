import pytest
from app.services.metrics import MetricsService, metrics_service


def test_dispatch_success_rate_all_success():
    svc = MetricsService()
    svc.add_dispatch_event(success=True)
    svc.add_dispatch_event(success=True)
    assert svc.calculate_dispatch_success_rate() == 100.0


def test_dispatch_success_rate_mixed():
    svc = MetricsService()
    svc.add_dispatch_event(success=True)
    svc.add_dispatch_event(success=False)
    assert svc.calculate_dispatch_success_rate() == 50.0


def test_dispatch_success_rate_empty():
    svc = MetricsService()
    assert svc.calculate_dispatch_success_rate() == 100.0  # vacuously passing


def test_check_launch_targets_pass():
    svc = MetricsService()
    for _ in range(97):
        svc.add_record({"status": "Ready", "human_edits": False, "latency_seconds": 5.0})
    for _ in range(3):
        svc.add_record({"status": "Ready", "human_edits": True, "latency_seconds": 5.0})
    for _ in range(2):
        svc.add_dispatch_event(success=True)
    result = svc.check_launch_targets(
        straight_through_target=95.0,
        review_rate_target=2.0,
        latency_p95_target_s=30.0,
        dispatch_success_target=99.0,
    )
    # 97/100 straight-through = 97% ✓, review = 3/100 = 3% ✗
    assert result["straight_through"]["pass"] is True
    assert result["review_rate"]["pass"] is False


def test_check_launch_targets_latency_fail():
    svc = MetricsService()
    for _ in range(100):
        svc.add_record({"status": "Ready", "human_edits": False, "latency_seconds": 40.0})
    result = svc.check_launch_targets(
        straight_through_target=95.0,
        review_rate_target=2.0,
        latency_p95_target_s=30.0,
        dispatch_success_target=99.0,
    )
    assert result["latency_p95"]["pass"] is False


import time
from unittest.mock import MagicMock


def test_classify_endpoint_records_metrics():
    """After classification, _record_classification_metrics pushes rows into metrics_service."""
    metrics_service.clear_records()

    from app.routers.uploads import _record_classification_metrics
    rows = [
        MagicMock(status="Ready", review_required=False),
        MagicMock(status="Needs Review", review_required=True),
    ]
    upload_start = time.monotonic() - 2.5
    _record_classification_metrics(rows, upload_start)

    assert len(metrics_service.classification_records) == 2
    assert metrics_service.classification_records[0]["status"] == "Ready"
    assert metrics_service.classification_records[1]["status"] == "Needs Review"
    assert metrics_service.classification_records[0]["latency_seconds"] == pytest.approx(2.5, abs=0.5)
