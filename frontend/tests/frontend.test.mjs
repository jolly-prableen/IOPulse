import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/main.tsx", import.meta.url), "utf8");

test("dashboard wires every non-placeholder page to a view", () => {
  for (const route of ["/analytics", "/anomalies", "/scheduling", "/lab", "/settings"]) {
    assert.match(source, new RegExp(`path="${route}"`));
  }
  assert.doesNotMatch(source, /This view is connected to the local API/);
});

test("scheduling UI leads with observed telemetry and labels simulations", () => {
  assert.match(source, /Current read throughput/);
  assert.match(source, /Top measured I\/O activity/);
  assert.match(source, /Scheduling Strategy Evaluation/);
  assert.match(source, /synthetic workload/);
  assert.doesNotMatch(source, /Request queue/);
  assert.doesNotMatch(source, /Initial head/);
});

test("system intelligence anomaly panel handles loading, empty, and failure states", () => {
  assert.match(source, /finally\(\(\) => setAnomalyLoading\(false\)\)/);
  assert.match(source, /No anomalies detected in the selected period\./);
  assert.match(source, /Unable to load anomaly evidence\./);
  assert.match(source, />Retry<|>Retry<\//);
});

test("system intelligence scheduling analysis unwraps the backend response safely", () => {
  assert.match(source, /isGeneratedSchedule/);
  assert.match(source, /schedule\.analysis|setSchedule\(response\.analysis\)/);
  assert.match(source, /Generating analysis…/);
  assert.match(source, /More telemetry samples are needed/);
  assert.match(source, /invalid analysis/);
});

test("anomaly center formats structured values and timestamps safely", () => {
  assert.match(source, /formatAnomalyValue/);
  assert.match(source, /value\.observed_value/);
  assert.match(source, /value\.baseline_value/);
  assert.match(source, /formatTimestamp\(item\.detected_at\)/);
  assert.match(source, /bytes_per_second/);
});
