from __future__ import annotations

import csv
import io
import json
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

import psutil
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from intelligence.io_anomaly import analyze_io_health
from intelligence.io_classifier import ProcessIOClassifier
from intelligence.io_disk_bridge import (
    analyze_disk_scheduling,
    analyze_process_io_scheduling,
    derive_request_workload,
)
from intelligence.io_metrics import ProcessIOCollector
from memory.fragmentation import (
    calculate_external_fragmentation,
    calculate_internal_fragmentation,
)
from memory.monitor import get_process_memory, get_system_memory
from memory.page_replacement import fifo, lru, optimal
from dashboard.alert_engine import AlertEngine
from process_concurrency.scheduling.integration import schedule_processes
from process_concurrency.deadlock.bankers_algorithm import bankers_algorithm


class Settings(BaseModel):
    refresh_interval: float = Field(2.0, ge=0.5, le=60)
    history_window: int = Field(60, ge=5, le=600)
    cpu_threshold: float = Field(50.0, gt=0)
    io_threshold: float = Field(1_000_000.0, gt=0)


class SchedulingRequest(BaseModel):
    requests: list[int] = Field(default_factory=list, max_length=1000)
    initial_head: int = Field(ge=0)
    disk_size: int = Field(gt=0, le=1_000_000)
    direction: Literal["left", "right"] = "right"

    @field_validator("requests")
    @classmethod
    def requests_are_non_negative(cls, value: list[int]) -> list[int]:
        if any(request < 0 for request in value):
            raise ValueError("requests must be non-negative")
        return value


class WorkloadRequest(SchedulingRequest):
    metrics: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)


class PageReplacementRequest(BaseModel):
    pages: list[int] = Field(max_length=10_000)
    frames: int = Field(gt=0, le=1000)
    algorithm: Literal["FIFO", "LRU", "OPTIMAL", "ALL"] = "ALL"

    @field_validator("pages")
    @classmethod
    def pages_are_non_negative(cls, value: list[int]) -> list[int]:
        if any(page < 0 for page in value):
            raise ValueError("pages must be non-negative")
        return value


class InternalFragmentationRequest(BaseModel):
    allocations: list[dict[str, int]] = Field(max_length=10_000)


class ExternalFragmentationRequest(BaseModel):
    total_memory: int = Field(gt=0)
    blocks: list[dict[str, Any]] = Field(max_length=10_000)


class CpuSchedulingRequest(BaseModel):
    algorithm: Literal["fcfs", "sjf", "priority", "round_robin"] = "fcfs"
    processes: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    time_quantum: float | None = Field(default=None, gt=0)


class BankersRequest(BaseModel):
    available: list[int] = Field(min_length=1, max_length=50)
    allocation: list[list[int]] = Field(min_length=1, max_length=100)
    maximum: list[list[int]] = Field(min_length=1, max_length=100)


class CollectorService:
    def __init__(self) -> None:
        self.collector = ProcessIOCollector()
        self.classifier = ProcessIOClassifier()
        self.alerts = AlertEngine()
        self.settings = Settings()
        self._history: deque[dict[str, Any]] = deque(maxlen=self.settings.history_window)
        self._latest: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def configure(self, settings: Settings) -> Settings:
        with self._lock:
            self.settings = settings
            self._history = deque(self._history, maxlen=settings.history_window)
            self.classifier = ProcessIOClassifier(
                cpu_threshold=settings.cpu_threshold,
                io_threshold=settings.io_threshold,
            )
        return settings

    def collect_once(self) -> None:
        metrics = self.collector.collect_all()
        enriched = []
        for item in metrics:
            classification = self.classifier.classify(item)
            enriched.append({**item, "classification": classification})
        with self._lock:
            self._latest = enriched
            self._history.append(
                {
                    "timestamp": time.time(),
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "processes": enriched,
                    "system": get_system_memory(),
                }
            )

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.collect_once()
            except Exception:
                # A failed sample must not stop future collection cycles.
                pass
            with self._lock:
                interval = self.settings.refresh_interval
            self._stop.wait(max(0.1, interval - (time.monotonic() - started)))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="iopulse-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            history = list(self._history)
            processes = list(self._latest)
        system = get_system_memory()
        anomaly_count = 0
        for process in processes:
            result = analyze_io_health(self.collector.get_process_history(process["pid"]))
            anomaly_count += int(result["any_anomaly"])
        return {
            "system": system,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "processes": processes,
            "history": history,
            "anomaly_count": anomaly_count,
            "collection_status": "collecting" if self._thread and self._thread.is_alive() else "stopped",
        }


service = CollectorService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    service.start()
    yield
    service.stop()


app = FastAPI(title="IO Pulse API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "iopulse", "mode": "local-only"}


@app.get("/api/system/summary")
def system_summary() -> dict[str, Any]:
    return service.snapshot()


@app.get("/api/system/memory")
def system_memory() -> dict[str, Any]:
    return {"system": get_system_memory(), "processes": get_process_memory(top_n=100)}


@app.get("/api/processes")
def processes(
    search: str | None = None,
    classification: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    items = service.snapshot()["processes"]
    if search:
        needle = search.casefold()
        items = [p for p in items if needle in str(p["pid"]) or needle in p["name"].casefold()]
    if classification:
        items = [p for p in items if p.get("classification", {}).get("classification") == classification]
    return {"items": items[:limit], "count": len(items)}


@app.get("/api/processes/{pid}/history")
def process_history(pid: int) -> list[dict[str, Any]]:
    if pid <= 0:
        raise HTTPException(400, "pid must be positive")
    return service.collector.get_process_history(pid)


@app.get("/api/analytics/io")
def io_analytics() -> dict[str, Any]:
    snapshot = service.snapshot()
    return {"history": snapshot["history"], "processes": snapshot["processes"]}


@app.get("/api/anomalies")
def anomalies() -> dict[str, Any]:
    def expose_values(result: dict[str, Any]) -> dict[str, Any]:
        detector_type = result.get("type")
        values = dict(result)
        if detector_type == "io_spike":
            values.update({
                "observed_value": result.get("current_rate"),
                "baseline_value": result.get("baseline_rate"),
                "value_unit": "bytes_per_second",
            })
        elif detector_type == "sustained_high_io":
            values.update({
                "observed_value": result.get("average_high_rate"),
                "baseline_value": result.get("thresholds", {}).get("high_rate"),
                "value_unit": "bytes_per_second",
            })
        elif detector_type == "rw_ratio_shift":
            values.update({
                "observed_value": result.get("current_ratio"),
                "baseline_value": result.get("baseline_ratio"),
                "value_unit": "read_write_ratio",
            })
        elif detector_type == "io_stall":
            values.update({
                "observed_value": None,
                "baseline_value": result.get("last_active_rate"),
                "value_unit": "bytes_per_second",
            })
        return values

    found = []
    for process in service.snapshot()["processes"]:
        result = analyze_io_health(service.collector.get_process_history(process["pid"]))
        if result["any_anomaly"]:
            found.append(
                {
                    "pid": process["pid"],
                    "name": process["name"],
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    **{
                        detector: expose_values(value)
                        if isinstance(value, dict) else value
                        for detector, value in result.items()
                    },
                }
            )
            service.alerts.add_io_anomaly_alerts(result, process["pid"], process["name"])
    return {"items": found, "alerts": [alert.as_dict() for alert in service.alerts.alerts]}


@app.post("/api/scheduling/simulate")
def scheduling_simulate(request: SchedulingRequest) -> dict[str, Any]:
    if request.initial_head >= request.disk_size or any(r >= request.disk_size for r in request.requests):
        raise HTTPException(422, "head and requests must be within disk_size")
    return analyze_disk_scheduling(
        request.requests, request.initial_head, request.disk_size, request.direction
    )


@app.post("/api/scheduling/compare")
def scheduling_compare(request: SchedulingRequest) -> dict[str, Any]:
    return scheduling_simulate(request)


@app.post("/api/scheduling/generate-workload")
def generate_workload(request: WorkloadRequest) -> dict[str, Any]:
    queue = derive_request_workload(request.metrics, disk_size=request.disk_size)
    return {
        "synthetic": True,
        "mapping": "deterministic MD5(pid, counter, read/write salt), biased by observed read/write activity",
        "requests": queue,
        "analysis": analyze_disk_scheduling(queue, request.initial_head, request.disk_size, request.direction),
    }


@app.post("/api/os-lab/page-replacement")
def page_replacement(request: PageReplacementRequest) -> dict[str, Any]:
    algorithms = {"FIFO": fifo, "LRU": lru, "OPTIMAL": optimal}
    selected = algorithms if request.algorithm == "ALL" else {request.algorithm: algorithms[request.algorithm]}
    try:
        return {"results": {name: fn(request.pages, request.frames) for name, fn in selected.items()}}
    except (ValueError, ZeroDivisionError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/os-lab/fragmentation/internal")
def internal_fragmentation(request: InternalFragmentationRequest) -> dict[str, Any]:
    try:
        return calculate_internal_fragmentation(request.allocations)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/os-lab/fragmentation/external")
def external_fragmentation(request: ExternalFragmentationRequest) -> dict[str, Any]:
    try:
        return calculate_external_fragmentation(request.total_memory, request.blocks)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/os-lab/cpu-scheduling")
def cpu_scheduling(request: CpuSchedulingRequest) -> dict[str, Any]:
    try:
        return schedule_processes(request.algorithm, request.processes, request.time_quantum)
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/os-lab/deadlock/bankers")
def deadlock_bankers(request: BankersRequest) -> dict[str, Any]:
    try:
        return bankers_algorithm(request.available, request.allocation, request.maximum)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/settings")
def get_settings() -> Settings:
    return service.settings


@app.put("/api/settings")
def update_settings(settings: Settings) -> Settings:
    return service.configure(settings)


@app.get("/api/export")
def export_data(format: Literal["json", "csv"] = "json") -> StreamingResponse:
    data = service.snapshot()
    if format == "json":
        content = json.dumps(data, default=str)
        return StreamingResponse(io.StringIO(content), media_type="application/json")
    output = io.StringIO()
    rows = data["processes"]
    writer = csv.DictWriter(output, fieldnames=["pid", "name", "cpu_percent", "memory_percent", "total_io_bytes_per_sec"])
    writer.writeheader()
    writer.writerows({key: row.get(key) for key in writer.fieldnames} for row in rows)
    return StreamingResponse(io.StringIO(output.getvalue()), media_type="text/csv")
