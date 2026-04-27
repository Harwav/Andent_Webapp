import pytest
from app.services.metrics import MetricsService


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
