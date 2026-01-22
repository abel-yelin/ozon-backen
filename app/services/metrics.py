"""Prometheus metrics for Image Studio."""
from __future__ import annotations

import time
from contextlib import contextmanager
from prometheus_client import Counter, Histogram, Gauge

# Metrics
images_generated = Counter(
    'image_studio_images_generated_total',
    'Total images generated',
    ['mode', 'status']
)

generation_duration = Histogram(
    'image_studio_generation_duration_seconds',
    'Image generation duration',
    ['mode']
)

active_jobs = Gauge(
    'image_studio_active_jobs',
    'Currently active jobs'
)

queue_size = Gauge(
    'image_studio_queue_size',
    'Jobs waiting in queue'
)

async_operations = Counter(
    'image_studio_async_operations_total',
    'Total async operations performed',
    ['operation_type', 'status']
)

download_duration = Histogram(
    'image_studio_download_duration_seconds',
    'Image download duration',
    ['source']
)

upload_duration = Histogram(
    'image_studio_upload_duration_seconds',
    'R2 upload duration'
)

webp_compression_ratio = Histogram(
    'image_studio_webp_compression_ratio',
    'WebP compression ratio (original_size / webp_size)',
    buckets=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 10.0]
)


@contextmanager
def track_generation(mode: str):
    """Context manager to track generation metrics.

    Usage:
        with track_generation("batch_series_generate"):
            # ... processing logic ...
    """
    active_jobs.inc()
    start_time = time.time()

    try:
        yield
    except Exception:
        duration = time.time() - start_time
        generation_duration.labels(mode=mode).observe(duration)
        images_generated.labels(mode=mode, status="failed").inc()
        active_jobs.dec()
        raise

    duration = time.time() - start_time
    generation_duration.labels(mode=mode).observe(duration)
    images_generated.labels(mode=mode, status="success").inc()
    active_jobs.dec()


@contextmanager
def track_async_operation(operation_type: str):
    """Context manager to track async operation metrics.

    Usage:
        with track_async_operation("download"):
            await download_file(...)
    """
    start_time = time.time()

    try:
        yield
    except Exception:
        duration = time.time() - start_time
        async_operations.labels(operation_type=operation_type, status="failed").inc()
        raise

    duration = time.time() - start_time
    async_operations.labels(operation_type=operation_type, status="success").inc()


def update_queue_size(size: int):
    """Update queue size gauge."""
    queue_size.set(size)


def record_compression_ratio(ratio: float):
    """Record WebP compression ratio."""
    webp_compression_ratio.observe(ratio)


def get_metrics_summary() -> dict:
    """Get summary of current metrics (for debugging)."""
    from prometheus_client import REGISTRY

    summary = {}
    for metric in REGISTRY.collect():
        if metric.name.startswith('image_studio_'):
            samples = {}
            for sample in metric.samples:
                label_str = ','.join(f"{k}={v}" for k, v in sample.labels.items())
                samples[label_str or 'value'] = sample.value
            summary[metric.name] = samples

    return summary
