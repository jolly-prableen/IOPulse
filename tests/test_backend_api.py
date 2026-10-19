from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_is_local_only() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "local-only"


def test_anomalies_endpoint_returns_frontend_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["items"], list)
    assert isinstance(data["alerts"], list)


def test_anomaly_detector_values_are_exposed_with_units() -> None:
    from intelligence.io_anomaly import analyze_io_health

    spike = analyze_io_health(
        [{"total_io_bytes_per_sec": 20_000.0}] * 3
        + [{"total_io_bytes_per_sec": 200_000.0}]
    )["io_spike"]
    sustained = analyze_io_health(
        [{"total_io_bytes_per_sec": 6_000_000.0}] * 5
    )["sustained_high_io"]
    ratio = analyze_io_health(
        [{"read_write_ratio": 1.0, "total_io_bytes_per_sec": 1.0}] * 5
        + [{"read_write_ratio": 6.0, "total_io_bytes_per_sec": 1.0}]
    )["rw_ratio_shift"]
    assert spike["current_rate"] == 200_000.0
    assert spike["baseline_rate"] == 20_000.0
    assert sustained["average_high_rate"] == 6_000_000.0
    assert sustained["thresholds"]["high_rate"] == 5_000_000.0
    assert ratio["current_ratio"] == 6.0
    assert ratio["baseline_ratio"] == 1.0


def test_generated_workload_returns_nested_analysis_contract() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/scheduling/generate-workload",
            json={
                "metrics": [
                    {
                        "pid": 123,
                        "total_io_bytes_per_sec": 5000,
                        "read_bytes_per_sec": 3000,
                        "write_bytes_per_sec": 2000,
                    }
                ],
                "initial_head": 0,
                "disk_size": 200,
                "direction": "right",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["synthetic"] is True
    assert isinstance(data["requests"], list)
    assert set(data["analysis"]["results"]) == {"FCFS", "SSTF", "SCAN", "C-SCAN"}


def test_scheduling_comparison_uses_one_validated_workload() -> None:
    payload = {
        "requests": [98, 183, 37, 122, 14, 124, 65, 67],
        "initial_head": 53,
        "disk_size": 200,
        "direction": "right",
    }
    with TestClient(app) as client:
        response = client.post("/api/scheduling/compare", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert set(data["results"]) == {"FCFS", "SSTF", "SCAN", "C-SCAN"}
    assert data["request_count"] == len(payload["requests"])


def test_scheduling_rejects_out_of_bounds_requests() -> None:
    payload = {"requests": [200], "initial_head": 0, "disk_size": 200}
    with TestClient(app) as client:
        response = client.post("/api/scheduling/simulate", json=payload)
    assert response.status_code == 422


def test_page_replacement_can_compare_all_algorithms() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/os-lab/page-replacement",
            json={"pages": [1, 2, 3, 1, 4], "frames": 3, "algorithm": "ALL"},
        )
    assert response.status_code == 200
    assert set(response.json()["results"]) == {"FIFO", "LRU", "OPTIMAL"}


def test_settings_reject_out_of_range_collection_interval() -> None:
    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={
                "refresh_interval": 0.1,
                "history_window": 60,
                "cpu_threshold": 50,
                "io_threshold": 1_000_000,
            },
        )
    assert response.status_code == 422


def test_export_returns_requested_content_type() -> None:
    with TestClient(app) as client:
        response = client.get("/api/export?format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "pid,name" in response.text


def test_os_lab_cpu_and_deadlock_endpoints_use_existing_algorithms() -> None:
    with TestClient(app) as client:
        cpu = client.post(
            "/api/os-lab/cpu-scheduling",
            json={
                "algorithm": "fcfs",
                "processes": [
                    {"pid": "P1", "arrival_time": 0, "burst_time": 3},
                    {"pid": "P2", "arrival_time": 1, "burst_time": 2},
                ],
            },
        )
        deadlock = client.post(
            "/api/os-lab/deadlock/bankers",
            json={
                "available": [3, 3, 2],
                "allocation": [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1]],
                "maximum": [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2]],
            },
        )
    assert cpu.status_code == 200
    assert cpu.json()["execution_sequence"] == ["P1", "P2"]
    assert deadlock.status_code == 200
    assert deadlock.json()["safe"] is True


def test_system_summary_history_contains_measured_cpu_samples() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/summary")
    assert response.status_code == 200
    history = response.json()["history"]
    if history:
        assert isinstance(history[-1]["cpu_percent"], (int, float))
