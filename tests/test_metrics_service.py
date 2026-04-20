"""Phase 3: Metrics Service Tests (TDD)"""
import pytest
from andent_web.app.services.metrics import MetricsService


class TestMetricsService:
    """Test metrics calculation for validation."""

    def setup_method(self):
        """Create fresh MetricsService for each test."""
        self.service = MetricsService()

    def test_straight_through_rate_calculation(self):
        """Test straight-through rate formula.
        
        Formula: (ready_without_edit / total) * 100
        Target: >= 95%
        """
        # Add 95 ready records without edit
        for i in range(95):
            self.service.add_record({"status": "Ready", "human_edits": False})
        # Add 5 that needed review
        for i in range(5):
            self.service.add_record({"status": "Needs Review", "human_edits": True})
        
        rate = self.service.calculate_straight_through_rate()
        assert rate == 95.0
        assert rate >= 95.0  # Target met

    def test_human_review_rate_calculation(self):
        """Test human review rate formula.
        
        Formula: (needs_review + check) / total * 100
        Target: <= 2%
        """
        # Add 98 ready records
        for i in range(98):
            self.service.add_record({"status": "Ready"})
        # Add 2 needs review
        self.service.add_record({"status": "Needs Review"})
        self.service.add_record({"status": "Check"})
        
        rate = self.service.calculate_human_review_rate()
        assert rate == 2.0
        assert rate <= 2.0  # Target met

    def test_latency_percentile_p50(self):
        """Test p50 latency calculation."""
        # Add records with latencies
        latencies = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
        for lat in latencies:
            self.service.add_record({"latency_seconds": lat})
        
        percentiles = self.service.calculate_latency_percentiles()
        # p50 at index 5 (50% of 10)
        assert percentiles["p50"] == 35

    def test_latency_percentile_p95(self):
        """Test p95 latency calculation."""
        # Use realistic latency values that meet <30s target
        latencies = [5, 8, 10, 12, 15, 18, 20, 22, 25, 28]
        for lat in latencies:
            self.service.add_record({"latency_seconds": lat})
        
        percentiles = self.service.calculate_latency_percentiles()
        assert percentiles["p95"] <= 30  # Target: <30s

    def test_metrics_aggregation_from_db(self):
        """Test metrics can be aggregated from database rows."""
        # Mock classification rows
        rows = [
            {"status": "Ready", "confidence": 0.9},
            {"status": "Ready", "confidence": 0.85},
            {"status": "Check", "confidence": 0.6},
            {"status": "Ready", "confidence": 0.92},
        ]
        for row in rows:
            self.service.add_record(row)
        
        distribution = self.service.get_confidence_distribution()
        assert distribution["high"] == 3  # 3 with confidence >= 0.8
        assert distribution["medium"] == 1  # 1 with 0.5-0.8
        assert distribution["low"] == 0