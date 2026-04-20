"""Metrics API router for dashboard."""
from datetime import datetime, timezone
from fastapi import APIRouter

from ..services.metrics import metrics_service

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/")
async def get_metrics() -> dict:
    """Get current classification metrics."""
    return metrics_service.get_metrics_summary()


@router.get("/confidence-distribution")
async def get_confidence_distribution() -> dict:
    """Get confidence level distribution."""
    return metrics_service.get_confidence_distribution()


@router.get("/latency-percentiles")
async def get_latency_percentiles() -> dict:
    """Get latency percentile statistics."""
    return metrics_service.calculate_latency_percentiles()


@router.post("/reset")
async def reset_metrics() -> dict:
    """Reset all metrics (for testing)."""
    metrics_service.clear_records()
    return {"status": "reset", "timestamp": datetime.now(timezone.utc).isoformat()}