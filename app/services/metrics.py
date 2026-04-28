"""Phase 3: Metrics Service for classification accuracy tracking."""
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import statistics


class MetricsService:
    """Calculate classification metrics for accuracy validation."""

    def __init__(self):
        self.classification_records: list[dict[str, Any]] = []
        self.dispatch_events: list[dict] = []

    def add_record(self, record: dict[str, Any]) -> None:
        """Add a classification record for metrics calculation."""
        self.classification_records.append(record)

    def calculate_straight_through_rate(self) -> float:
        """Calculate straight-through rate (ready without edit / total).
        
        Target: ≥95%
        """
        if not self.classification_records:
            return 0.0

        ready_without_edit = sum(
            1 for r in self.classification_records
            if r.get("status") == "Ready" and not r.get("human_edits", False)
        )
        total = len(self.classification_records)
        return (ready_without_edit / total) * 100 if total > 0 else 0.0

    def calculate_human_review_rate(self) -> float:
        """Calculate human review rate (needs_review + check / total).
        
        Target: ≤2%
        """
        if not self.classification_records:
            return 0.0

        needs_review = sum(
            1 for r in self.classification_records
            if r.get("status") in ("Needs Review", "Check") or r.get("human_edits", False)
        )
        total = len(self.classification_records)
        return (needs_review / total) * 100 if total > 0 else 0.0

    def get_confidence_distribution(self) -> dict[str, int]:
        """Get confidence distribution buckets.
        
        Buckets:
        - high: ≥0.8
        - medium: 0.5-0.8
        - low: <0.5
        """
        distribution = {"high": 0, "medium": 0, "low": 0}

        for r in self.classification_records:
            confidence = r.get("confidence", 0.5)
            if confidence >= 0.8:
                distribution["high"] += 1
            elif confidence >= 0.5:
                distribution["medium"] += 1
            else:
                distribution["low"] += 1

        return distribution

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get comprehensive metrics summary."""
        return {
            "straight_through_rate": self.calculate_straight_through_rate(),
            "human_review_rate": self.calculate_human_review_rate(),
            "confidence_distribution": self.get_confidence_distribution(),
            "total_classifications": len(self.classification_records),
            "latency_percentiles": self.calculate_latency_percentiles(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def calculate_latency_percentiles(self) -> dict[str, float]:
        """Calculate latency percentiles (p50, p95, p99).
        
        Target p95: <30s
        """
        latencies = [
            r.get("latency_seconds", 0)
            for r in self.classification_records
            if "latency_seconds" in r
        ]

        if not latencies:
            return {"p50": 0, "p95": 0, "p99": 0}

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        def percentile(p: float) -> float:
            """Calculate percentile value."""
            index = int(n * p)
            if index >= n:
                return sorted_latencies[-1]
            return sorted_latencies[index]

        return {
            "p50": percentile(0.50),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
        }

    def add_dispatch_event(self, *, success: bool) -> None:
        """Record a PreFormServer dispatch outcome."""
        self.dispatch_events.append({"success": success})

    def calculate_dispatch_success_rate(self) -> float:
        """Calculate dispatch success rate. Target: >=99%."""
        if not self.dispatch_events:
            return 0.0
        successes = sum(1 for e in self.dispatch_events if e["success"])
        return (successes / len(self.dispatch_events)) * 100.0

    def check_launch_targets(
        self,
        *,
        straight_through_target: float = 95.0,
        review_rate_target: float = 2.0,
        latency_p95_target_s: float = 30.0,
        dispatch_success_target: float = 99.0,
    ) -> dict[str, Any]:
        """Return pass/fail for every PRD launch criterion."""
        st_rate = self.calculate_straight_through_rate()
        review_rate = self.calculate_human_review_rate()
        latency = self.calculate_latency_percentiles()
        dispatch_rate = self.calculate_dispatch_success_rate()
        return {
            "straight_through": {
                "value": st_rate,
                "target": straight_through_target,
                "pass": st_rate >= straight_through_target,
            },
            "review_rate": {
                "value": review_rate,
                "target": review_rate_target,
                "pass": review_rate <= review_rate_target,
            },
            "latency_p95": {
                "value": latency["p95"],
                "target": latency_p95_target_s,
                "pass": latency["p95"] <= latency_p95_target_s or not self.classification_records,
            },
            "dispatch_success": {
                "value": dispatch_rate,
                "target": dispatch_success_target,
                "pass": dispatch_rate >= dispatch_success_target,
            },
            "overall_pass": all([
                st_rate >= straight_through_target,
                review_rate <= review_rate_target,
                latency["p95"] <= latency_p95_target_s or not self.classification_records,
                dispatch_rate >= dispatch_success_target,
            ]),
        }

    def clear_records(self) -> None:
        """Clear all records for fresh calculation."""
        self.classification_records.clear()
        self.dispatch_events.clear()


# Global metrics service instance
metrics_service = MetricsService()
