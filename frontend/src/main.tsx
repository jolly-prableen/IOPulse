import { StrictMode, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";
import "./styles.css";

const API = "http://127.0.0.1:8000/api";
type Process = { pid: number; name: string; cpu_percent: number; memory_percent: number; read_bytes_per_sec?: number; write_bytes_per_sec?: number; total_io_bytes_per_sec: number; read_write_ratio?: number; state: string; classification?: { classification: string; reason: string } };
type Sample = { timestamp: number; cpu_percent?: number; processes: Process[]; system: { ram_percent: number; swap_percent: number } };
type Snapshot = { system: { ram_percent: number; swap_percent: number }; cpu_percent: number; processes: Process[]; history: Sample[]; anomaly_count: number; collection_status: string };
type Settings = { refresh_interval: number; history_window: number; cpu_threshold: number; io_threshold: number };
type Anomaly = { pid: number; name: string; [key: string]: unknown };
type ScheduleResult = { request_order: number[]; total_head_movement: number; average_seek_distance: number; steps: { from: number; to: number; distance: number }[] };
type ScheduleResponse = { results: Record<string, ScheduleResult>; recommended_algorithm: string; reason: string; request_count: number };
type GeneratedSchedule = { synthetic: boolean; mapping: string; requests: number[]; analysis: ScheduleResponse };
function isGeneratedSchedule(value: unknown): value is GeneratedSchedule {
  if (!value || typeof value !== "object") return false;
  const result = value as Partial<GeneratedSchedule>;
  const analysis = result.analysis;
  return result.synthetic === true && Array.isArray(result.requests) && Boolean(analysis) &&
    typeof analysis?.request_count === "number" && typeof analysis?.results === "object";
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}
const post = <T,>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
const rate = (value: number) => value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB/s` : value >= 1024 ? `${(value / 1024).toFixed(1)} KB/s` : `${Math.round(value)} B/s`;
function formatTimestamp(value: unknown): string {
  if (typeof value !== "number" && typeof value !== "string") return "Unavailable";
  const parsed = typeof value === "number"
    ? new Date(value < 100_000_000_000 ? value * 1000 : value)
    : new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : parsed.toLocaleString();
}
function formatAnomalyValue(value: unknown, unit: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Unavailable";
  if (unit === "bytes_per_second") return rate(value);
  if (unit === "read_write_ratio") return Number.isFinite(value) ? value.toFixed(2) : "Unavailable";
  return String(value);
}

function State({ children, error = false }: { children: ReactNode; error?: boolean }) { return <div className={error ? "state error" : "state"}>{children}</div>; }
function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) { return <article className="metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</article>; }
function Panel({ title, eyebrow, action, children }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode }) { return <section className="panel"><div className="panel-title"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>{action}</div>{children}</section>; }
function Trend({ values, second, name }: { values: number[]; second?: number[]; name: string }) { const max = Math.max(...values, ...(second ?? []), 1); const points = (list: number[]) => list.map((v, i) => `${i / Math.max(list.length - 1, 1) * 100},${94 - (v / max) * 82}`).join(" "); return <div className="chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={name}><path className="gridline" d="M0 94H100M0 53H100M0 12H100" /><polyline className="chart-line primary-line" points={points(values)} />{second && <polyline className="chart-line secondary-line" points={points(second)} />}</svg><div className="chart-axis"><span>Earlier</span><span>Latest</span></div></div>; }
function Empty({ text }: { text: string }) { return <State>{text}</State>; }

const navItems = [
  ["/", "⌂", "Overview"], ["/processes", "◉", "Process Explorer"], ["/analytics", "⌁", "I/O Analytics"],
  ["/anomalies", "!", "Anomaly Center"], ["/scheduling", "↝", "Scheduling Intelligence"], ["/lab", "▦", "System Intelligence"], ["/settings", "⚙", "Reports & Settings"],
];
function Layout({ children, paused, setPaused, snapshot }: { children: ReactNode; paused: boolean; setPaused: (v: boolean) => void; snapshot: Snapshot | null }) {
  const location = useLocation();
  const current = navItems.find(([path]) => path === "/" ? location.pathname === "/" : location.pathname.startsWith(path));
  const title = current?.[2] ?? "Workspace";
  useEffect(() => { document.title = `${title} · IO Pulse`; }, [title]);
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">◒</span><span>IO<span>Pulse</span></span></div><p className="eyebrow nav-title">WORKSPACE</p><nav aria-label="Primary navigation">{navItems.map(([path, icon, label]) => <NavLink end={path === "/"} to={path} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`} key={path}><span className="nav-icon">{icon}</span><span>{label}</span></NavLink>)}</nav><div className="sidebar-footer"><span className="status-dot" />Local collector<br /><small>Read-only monitoring</small></div></aside><main className="main"><header className="page-header"><div><p className="eyebrow">IO PULSE / {title.toUpperCase()}</p><h1>{title}</h1></div><button className="control" onClick={() => setPaused(!paused)}>{paused ? "Resume collection" : "Pause collection"}</button></header>{snapshot && <div className="collector-bar"><span className="status-dot" /> Collector {snapshot.collection_status} <span className="bar-sep">•</span> {snapshot.processes.length} rate samples <span className="bar-sep">•</span> Local-only telemetry</div>}{children}</main></div>;
}

function Overview({ snapshot }: { snapshot: Snapshot }) {
  const read = snapshot.history.map(s => s.processes.reduce((sum, p) => sum + (p.read_bytes_per_sec ?? 0), 0)); const write = snapshot.history.map(s => s.processes.reduce((sum, p) => sum + (p.write_bytes_per_sec ?? 0), 0));
  const cpu = snapshot.history.map(s => s.cpu_percent ?? 0); const memory = snapshot.history.map(s => s.system.ram_percent); const top = [...snapshot.processes].sort((a, b) => b.total_io_bytes_per_sec - a.total_io_bytes_per_sec).slice(0, 5);
  return <div className="page-stack"><section className="metrics"><Metric label="CPU utilization" value={`${snapshot.cpu_percent.toFixed(1)}%`} detail="Host-wide" /><Metric label="RAM utilization" value={`${snapshot.system.ram_percent.toFixed(1)}%`} /><Metric label="Visible processes" value={String(snapshot.processes.length)} /><Metric label="Read throughput" value={rate(read.at(-1) ?? 0)} /><Metric label="Write throughput" value={rate(write.at(-1) ?? 0)} /></section><div className="two-col"><Panel title="CPU & memory trend" eyebrow="OBSERVED HISTORY"><div className="legend"><span className="legend-cpu" />CPU <span className="legend-memory" />RAM</div>{snapshot.history.length > 1 ? <Trend values={cpu} second={memory} name="CPU and memory history" /> : <Empty text="Collecting history. Trends appear after two samples." />}</Panel><Panel title="Recent anomalies" eyebrow="ATTENTION"><div className="alert-summary">{snapshot.anomaly_count ? <><strong>{snapshot.anomaly_count}</strong><span>active process anomalies</span><NavLink to="/anomalies" className="text-link">Review alerts →</NavLink></> : <Empty text="No active anomalies detected." />}</div></Panel></div><Panel title="Top I/O processes" eyebrow="CURRENT SAMPLE" action={<NavLink to="/processes" className="text-link">View all processes →</NavLink>}><div className="table-wrap"><table><thead><tr><th>Process</th><th>PID</th><th>Read</th><th>Write</th><th>Classification</th></tr></thead><tbody>{top.map(p => <tr key={p.pid}><td><NavLink to={`/processes/${p.pid}`} className="process-link">{p.name}</NavLink></td><td>{p.pid}</td><td>{rate(p.read_bytes_per_sec ?? 0)}</td><td>{rate(p.write_bytes_per_sec ?? 0)}</td><td><span className="tag">{p.classification?.classification ?? "warming up"}</span></td></tr>)}</tbody></table>{!top.length && <Empty text="No accessible process rate samples yet." />}</div></Panel></div>;
}

function ProcessExplorer({ snapshot }: { snapshot: Snapshot }) {
  const [search, setSearch] = useState(""); const [filter, setFilter] = useState("ALL"); const [sort, setSort] = useState("total_io_bytes_per_sec"); const [page, setPage] = useState(0); const size = 12;
  const rows = useMemo(() => snapshot.processes.filter(p => (!search || `${p.pid} ${p.name}`.toLowerCase().includes(search.toLowerCase())) && (filter === "ALL" || p.classification?.classification === filter)).sort((a, b) => Number(b[sort as keyof Process] ?? 0) - Number(a[sort as keyof Process] ?? 0)), [snapshot.processes, search, filter, sort]);
  const shown = rows.slice(page * size, page * size + size); const pages = Math.max(1, Math.ceil(rows.length / size));
  return <Panel title="Process Explorer" eyebrow={`${rows.length} ACCESSIBLE PROCESSES`}><div className="toolbar"><input placeholder="Search PID or process name" value={search} onChange={e => { setSearch(e.target.value); setPage(0); }} aria-label="Search processes" /><select value={filter} onChange={e => setFilter(e.target.value)} aria-label="Filter classification"><option>ALL</option><option>CPU_BOUND</option><option>IO_BOUND</option><option>BALANCED</option><option>IDLE</option></select><select value={sort} onChange={e => setSort(e.target.value)} aria-label="Sort processes"><option value="total_io_bytes_per_sec">Sort: I/O</option><option value="cpu_percent">Sort: CPU</option><option value="memory_percent">Sort: memory</option><option value="pid">Sort: PID</option></select></div><div className="table-wrap"><table><thead><tr><th>PID</th><th>Process</th><th>CPU</th><th>Memory</th><th>Read</th><th>Write</th><th>Behavior</th><th>Status</th></tr></thead><tbody>{shown.map(p => <tr key={p.pid}><td><NavLink to={`/processes/${p.pid}`} className="process-link">{p.pid}</NavLink></td><td>{p.name}</td><td>{p.cpu_percent.toFixed(1)}%</td><td>{p.memory_percent.toFixed(1)}%</td><td>{rate(p.read_bytes_per_sec ?? 0)}</td><td>{rate(p.write_bytes_per_sec ?? 0)}</td><td><span className="tag">{p.classification?.classification ?? "warming up"}</span></td><td>{p.state}</td></tr>)}</tbody></table>{!shown.length && <Empty text="No processes match the current search and filter." />}</div><div className="pagination"><span>Showing {shown.length ? page * size + 1 : 0}–{Math.min((page + 1) * size, rows.length)} of {rows.length}</span><button className="control" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><button className="control" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</button></div></Panel>;
}

function ProcessDetail({ snapshot }: { snapshot: Snapshot }) {
  const { pid } = useParams(); const process = snapshot.processes.find(p => p.pid === Number(pid)); const [history, setHistory] = useState<Process[]>([]); const [alerts, setAlerts] = useState<Anomaly[]>([]); const [error, setError] = useState("");
  useEffect(() => { if (pid) { api<Process[]>(`/processes/${pid}/history`).then(setHistory).catch(e => setError(e.message)); api<{ items: Anomaly[] }>("/anomalies").then(data => setAlerts(data.items.filter(item => item.pid === Number(pid)))).catch(() => undefined); } }, [pid]);
  if (!process) return <State error>Process {pid} is not in the current accessible sample. It may have exited or denied access.</State>;
  return <div className="page-stack"><NavLink to="/processes" className="back-link">← Back to Process Explorer</NavLink><section className="metrics compact"><Metric label="Process" value={process.name} /><Metric label="CPU" value={`${process.cpu_percent.toFixed(1)}%`} /><Metric label="I/O rate" value={rate(process.total_io_bytes_per_sec)} /></section><Panel title={`${process.name} · PID ${process.pid}`} eyebrow="PROCESS DETAIL"><div className="detail-grid"><div><span className="detail-label">Classification</span><strong>{process.classification?.classification ?? "warming up"}</strong></div><div><span className="detail-label">Memory</span><strong>{process.memory_percent.toFixed(1)}%</strong></div><div><span className="detail-label">Status</span><strong>{process.state}</strong></div><div><span className="detail-label">Explanation</span><strong>{process.classification?.reason ?? "A second sample is required for classification."}</strong></div></div></Panel><Panel title="I/O history" eyebrow="BOUNDED PROCESS HISTORY">{error ? <State error>{error}</State> : history.length > 1 ? <Trend values={history.map(h => h.read_bytes_per_sec ?? 0)} second={history.map(h => h.write_bytes_per_sec ?? 0)} name="Process I/O history" /> : <Empty text="No historical rate data is available for this process." />}</Panel><Panel title="Related alerts" eyebrow="PROCESS ANOMALIES">{alerts.length ? alerts.map(alert => <div className="related-alert" key={`${alert.pid}-${alert.detected_at}`}>{Object.entries(alert).filter(([key]) => key !== "pid" && key !== "name").map(([key, value]) => <span key={key}><b>{key.replaceAll("_", " ")}:</b> {typeof value === "object" ? JSON.stringify(value) : String(value)}</span>)}</div>) : <Empty text="No active related alerts." />}</Panel></div>;
}

function Analytics({ snapshot }: { snapshot: Snapshot }) {
  const read = snapshot.history.map(s => s.processes.reduce((n, p) => n + (p.read_bytes_per_sec ?? 0), 0)); const write = snapshot.history.map(s => s.processes.reduce((n, p) => n + (p.write_bytes_per_sec ?? 0), 0)); const top = [...snapshot.processes].sort((a, b) => b.total_io_bytes_per_sec - a.total_io_bytes_per_sec).slice(0, 8); const ratio = read.reduce((a, b) => a + b, 0) / Math.max(write.reduce((a, b) => a + b, 0), 1);
  return <div className="page-stack"><div className="metrics compact"><Metric label="Read throughput" value={rate(read.at(-1) ?? 0)} /><Metric label="Write throughput" value={rate(write.at(-1) ?? 0)} /><Metric label="Read/write ratio" value={`${ratio.toFixed(2)} : 1`} detail="From observed counters" /></div><div className="two-col"><Panel title="Read throughput" eyebrow="OBSERVED BYTES / SECOND">{read.length > 1 ? <Trend values={read} name="Read throughput history" /> : <Empty text="Not enough history for a trend." />}</Panel><Panel title="Write throughput" eyebrow="OBSERVED BYTES / SECOND">{write.length > 1 ? <Trend values={write} name="Write throughput history" /> : <Empty text="Not enough history for a trend." />}</Panel></div><Panel title="I/O-heavy processes" eyebrow="CURRENT SAMPLE"><div className="table-wrap"><table><thead><tr><th>Process</th><th>Read</th><th>Write</th><th>Total</th><th>Ratio</th></tr></thead><tbody>{top.map(p => <tr key={p.pid}><td>{p.name} <small>PID {p.pid}</small></td><td>{rate(p.read_bytes_per_sec ?? 0)}</td><td>{rate(p.write_bytes_per_sec ?? 0)}</td><td>{rate(p.total_io_bytes_per_sec)}</td><td>{p.read_write_ratio === undefined ? "Unavailable" : Number.isFinite(p.read_write_ratio) ? p.read_write_ratio.toFixed(2) : "Read-only"}</td></tr>)}</tbody></table></div></Panel></div>;
}

function Anomalies() {
  const [data, setData] = useState<{ items: Anomaly[]; alerts: Record<string, unknown>[] } | null>(null); const [error, setError] = useState(""); const [severity, setSeverity] = useState("ALL");
  useEffect(() => { api<typeof data>("/anomalies").then(setData).catch(e => setError(e.message)); }, []);
  if (error) return <State error>Unable to load anomaly data: {error}</State>; if (!data) return <State>Loading anomaly detectors…</State>;
  const rows = data.items.flatMap(item => Object.entries(item).filter(([k, v]) => ["io_spike", "io_stall", "sustained_high_io", "rw_ratio_shift"].includes(k) && (v as { anomaly?: boolean }).anomaly).map(([type, value]) => ({ item, type, value: value as Record<string, unknown> }))).filter(row => severity === "ALL" || String(row.value.severity) === severity.toLowerCase());
  return <div className="page-stack"><Panel title="Anomaly Center" eyebrow="EXPLAINABLE DETECTION" action={<select value={severity} onChange={e => setSeverity(e.target.value)} aria-label="Filter anomaly severity"><option>ALL</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>}><p className="muted">Anomalies use real process histories and backend cooldown/deduplication. Values are not inferred when history is insufficient.</p><div className="anomaly-table-wrap"><table className="anomaly-table"><colgroup><col className="col-severity" /><col className="col-process" /><col className="col-detected" /><col className="col-type" /><col className="col-value" /><col className="col-value" /><col className="col-explanation" /></colgroup><thead><tr><th>Severity</th><th>Process</th><th>Detected</th><th>Type</th><th>Observed</th><th>Baseline</th><th>Explanation</th></tr></thead><tbody>{rows.map(({ item, type, value }) => <tr key={`${item.pid}-${type}`}><td><span className={`severity ${value.severity}`}>{String(value.severity).toUpperCase()}</span></td><td className="process-cell" title={item.name}>{item.name}<small>PID {item.pid}</small></td><td>{formatTimestamp(item.detected_at)}</td><td>{type.replaceAll("_", " ")}</td><td>{formatAnomalyValue(value.observed_value ?? (type === "io_spike" ? value.current_rate : type === "rw_ratio_shift" ? value.current_ratio : undefined), value.value_unit)}</td><td>{formatAnomalyValue(value.baseline_value ?? (type === "io_spike" ? value.baseline_rate : type === "rw_ratio_shift" ? value.baseline_ratio : undefined), value.value_unit)}</td><td className="explanation">{String(value.reason ?? "Detector reported an anomaly.")}</td></tr>)}</tbody></table>{!rows.length && <Empty text="No active anomalies match this filter." />}</div></Panel><Panel title="Normalized alert history"><div className="table-wrap"><table><thead><tr><th>Severity</th><th>Category</th><th>Process</th><th>Time</th><th>Message</th></tr></thead><tbody>{data.alerts.map((alert, i) => <tr key={i}><td><span className="tag">{String(alert.severity)}</span></td><td>{String(alert.category)}</td><td>{alert.pid ? `PID ${alert.pid}` : "System"}</td><td>{formatTimestamp(alert.timestamp)}</td><td>{String(alert.message)}</td></tr>)}</tbody></table>{!data.alerts.length && <Empty text="No normalized alerts have been recorded." />}</div></Panel></div>;
}

function Scheduling({ snapshot }: { snapshot: Snapshot }) {
  const [selectedPid, setSelectedPid] = useState<number | null>(null);
  const [history, setHistory] = useState<Process[]>([]);
  const [anomalies, setAnomalies] = useState<{ items: Anomaly[]; alerts: Record<string, unknown>[] } | null>(null);
  const [evaluation, setEvaluation] = useState<GeneratedSchedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const read = snapshot.history.map(sample => sample.processes.reduce((sum, process) => sum + (process.read_bytes_per_sec ?? 0), 0));
  const write = snapshot.history.map(sample => sample.processes.reduce((sum, process) => sum + (process.write_bytes_per_sec ?? 0), 0));
  const selected = snapshot.processes.find(process => process.pid === selectedPid) ?? null;
  const top = [...snapshot.processes].sort((a, b) => b.total_io_bytes_per_sec - a.total_io_bytes_per_sec).slice(0, 8);
  const processAnomalies = anomalies?.items.filter(item => item.pid === selectedPid) ?? [];
  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      api<{ items: Anomaly[]; alerts: Record<string, unknown>[] }>("/anomalies"),
      selectedPid ? api<Process[]>(`/processes/${selectedPid}/history`) : Promise.resolve([]),
    ]).then(([anomalyResponse, processHistory]) => {
      if (!active) return;
      setAnomalies(anomalyResponse);
      setHistory(processHistory);
      setError("");
    }).catch(errorValue => active && setError(errorValue instanceof Error ? errorValue.message : "Unable to load I/O analysis."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [selectedPid, snapshot.history.length, snapshot.processes.length]);
  const evaluate = async () => {
    try {
      setError("");
      setEvaluation(await post<GeneratedSchedule>("/scheduling/generate-workload", {
        metrics: snapshot.processes,
        initial_head: 0,
        disk_size: 200,
        direction: "right",
      }));
    } catch (errorValue) {
      setError(errorValue instanceof Error ? errorValue.message : "Unable to evaluate the observed workload.");
    }
  };
  const currentRead = selected?.read_bytes_per_sec ?? 0;
  const currentWrite = selected?.write_bytes_per_sec ?? 0;
  return <div className="page-stack">
    {error && <State error>{error}</State>}
    <section className="metrics compact">
      <Metric label="Current read throughput" value={rate(read.at(-1) ?? 0)} detail="Measured aggregate rate" />
      <Metric label="Current write throughput" value={rate(write.at(-1) ?? 0)} detail="Measured aggregate rate" />
      <Metric label="Observed I/O processes" value={String(snapshot.processes.length)} detail="Accessible rate samples" />
    </section>
    <div className="two-col">
      <Panel title="Read and write activity" eyebrow="OBSERVED HISTORY">{snapshot.history.length > 1 ? <><div className="legend"><span className="legend-cpu" />Read <span className="legend-memory" />Write</div><Trend values={read} second={write} name="Aggregate read and write throughput history" /></> : <Empty text="More collector samples are needed before historical activity can be shown." />}</Panel>
      <Panel title="Activity observations" eyebrow="EVIDENCE FROM MEASUREMENTS"><ul className="observation-list"><li>{snapshot.history.length > 1 ? `Aggregate I/O has ${snapshot.history.length} retained samples.` : "Historical I/O activity is not yet available."}</li><li>{top.length ? `${top[0].name} currently has the highest measured activity at ${rate(top[0].total_io_bytes_per_sec)}.` : "No accessible process has a measured I/O rate."}</li><li>{snapshot.anomaly_count ? `${snapshot.anomaly_count} process anomaly signal(s) are available for explanation.` : "No active anomaly signals are currently detected."}</li></ul></Panel>
    </div>
    <Panel title="Top measured I/O activity" eyebrow="CURRENT PROCESSES"><div className="table-wrap"><table><thead><tr><th>Process</th><th>PID</th><th>Read</th><th>Write</th><th>Ratio</th><th>Behavior</th></tr></thead><tbody>{top.map(process => <tr key={process.pid}><td><button className="process-link process-button" onClick={() => setSelectedPid(process.pid)}>{process.name}</button></td><td>{process.pid}</td><td>{rate(process.read_bytes_per_sec ?? 0)}</td><td>{rate(process.write_bytes_per_sec ?? 0)}</td><td>{process.read_write_ratio === undefined ? "Unavailable" : Number.isFinite(process.read_write_ratio) ? process.read_write_ratio.toFixed(2) : "Read-only"}</td><td><span className="tag">{process.classification?.classification ?? "Warming up"}</span></td></tr>)}</tbody></table>{!top.length && <Empty text="No measured process I/O is available yet." />}</div></Panel>
    <Panel title="Process I/O Analysis" eyebrow="SELECT A MONITORED PROCESS" action={<select value={selectedPid ?? ""} onChange={event => setSelectedPid(event.target.value ? Number(event.target.value) : null)} aria-label="Select monitored process"><option value="">Select process</option>{snapshot.processes.map(process => <option value={process.pid} key={process.pid}>{process.name} · PID {process.pid}</option>)}</select>}>{selected ? <div className="page-stack"><div className="metrics compact"><Metric label="Read rate" value={rate(currentRead)} /><Metric label="Write rate" value={rate(currentWrite)} /><Metric label="Read/write ratio" value={selected.read_write_ratio === undefined ? "Unavailable" : Number.isFinite(selected.read_write_ratio) ? selected.read_write_ratio.toFixed(2) : "Read-only"} /></div>{loading ? <State>Loading process history…</State> : history.length > 1 ? <Trend values={history.map(item => item.read_bytes_per_sec ?? 0)} second={history.map(item => item.write_bytes_per_sec ?? 0)} name={`${selected.name} read and write history`} /> : <Empty text="More samples are needed for this process trend." />}<p className="muted">{selected.classification?.reason ?? "Classification is unavailable until sufficient rate data exists."}</p>{processAnomalies.length ? <div className="related-alert">{processAnomalies.map(anomaly => <span key={`${anomaly.pid}-${String(anomaly.detected_at)}`}>Anomaly evidence available: {Object.keys(anomaly).filter(key => key.startsWith("io_") || key === "sustained_high_io").join(", ")}</span>)}</div> : <Empty text="No related anomaly evidence for this process." />}</div> : <Empty text="Select a monitored process to inspect its collected history and classification evidence." />}</Panel>
    <Panel title="Scheduling Strategy Evaluation" eyebrow="SECONDARY · SYNTHETIC ANALYSIS"><p className="muted">This optional evaluation derives a deterministic synthetic workload from the observed process I/O activity. Cylinder positions are not physical requests and cannot predict disk latency or storage performance.</p><button className="primary" onClick={evaluate}>Evaluate observed activity</button>{evaluation && <div className="page-stack"><div className="recommendation"><strong>{evaluation.analysis.recommended_algorithm}</strong><span>{evaluation.analysis.reason}</span></div><div className="evidence"><span>Generated requests: {evaluation.requests.length}</span><span>Mapping: {evaluation.mapping}</span></div><div className="schedule-grid">{Object.entries(evaluation.analysis.results).map(([name, result]) => <article className="schedule-card" key={name}><h3>{name}</h3><strong>{result.total_head_movement} simulated cylinders</strong><span>{result.average_seek_distance.toFixed(2)} average movement/request</span></article>)}</div></div>}</Panel>
  </div>;
}

function CpuSchedulingLab() {
  const [algorithm, setAlgorithm] = useState("fcfs"); const [quantum, setQuantum] = useState(2); const [processes, setProcesses] = useState('[{"pid":"P1","arrival_time":0,"burst_time":5},{"pid":"P2","arrival_time":1,"burst_time":3},{"pid":"P3","arrival_time":2,"burst_time":2}]'); const [result, setResult] = useState<Record<string, unknown> | null>(null); const [error, setError] = useState("");
  const run = async () => { try { setResult(await post("/os-lab/cpu-scheduling", { algorithm, processes: JSON.parse(processes), time_quantum: algorithm === "round_robin" ? quantum : null })); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "Invalid CPU scheduling input"); } };
  return <Panel title="CPU scheduling" eyebrow="OS LAB · SIMULATION"><div className="form-grid"><label>Algorithm<select value={algorithm} onChange={e => setAlgorithm(e.target.value)}><option value="fcfs">FCFS</option><option value="sjf">SJF</option><option value="priority">Priority</option><option value="round_robin">Round Robin</option></select></label><label>Time quantum<input type="number" min="0.1" value={quantum} onChange={e => setQuantum(Number(e.target.value))} /></label></div><label>Processes (JSON)<textarea value={processes} onChange={e => setProcesses(e.target.value)} /></label><button className="primary" onClick={run}>Run CPU schedule</button>{error && <p className="error">{error}</p>}{result && <pre className="json-result">{JSON.stringify(result, null, 2)}</pre>}</Panel>;
}

function DeadlockLab() {
  const [available, setAvailable] = useState("3,3,2"); const [allocation, setAllocation] = useState("[[0,1,0],[2,0,0],[3,0,2],[2,1,1]]"); const [maximum, setMaximum] = useState("[[7,5,3],[3,2,2],[9,0,2],[2,2,2]]"); const [result, setResult] = useState<{ safe: boolean; message: string; safe_sequence: string[] } | null>(null); const [error, setError] = useState("");
  const run = async () => { try { setResult(await post("/os-lab/deadlock/bankers", { available: available.split(",").map(Number), allocation: JSON.parse(allocation), maximum: JSON.parse(maximum) })); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "Invalid deadlock input"); } };
  return <Panel title="Deadlock avoidance" eyebrow="OS LAB · BANKER'S ALGORITHM"><div className="form-grid"><label>Available resources<textarea value={available} onChange={e => setAvailable(e.target.value)} /></label><label>Allocation matrix<textarea value={allocation} onChange={e => setAllocation(e.target.value)} /></label><label>Maximum matrix<textarea value={maximum} onChange={e => setMaximum(e.target.value)} /></label></div><button className="primary" onClick={run}>Check safe state</button>{error && <p className="error">{error}</p>}{result && <div className={`result-banner ${result.safe ? "safe" : "unsafe"}`}><strong>{result.message}</strong><span>{result.safe ? `Safe sequence: ${result.safe_sequence.join(" → ")}` : "No safe sequence exists."}</span></div>}</Panel>;
}

type MemoryProcess = { pid: number; name: string; memory_percent: number; memory_rss_mb: number | null };

function SystemIntelligence({ snapshot }: { snapshot: Snapshot }) {
  const [memoryProcesses, setMemoryProcesses] = useState<MemoryProcess[]>([]);
  const [anomalies, setAnomalies] = useState<{ items: Anomaly[]; alerts: Record<string, unknown>[] } | null>(null);
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleError, setScheduleError] = useState("");
  const [scheduleNotice, setScheduleNotice] = useState("");
  const [scheduleProcessCount, setScheduleProcessCount] = useState(0);
  const [scheduleReadRate, setScheduleReadRate] = useState(0);
  const [scheduleWriteRate, setScheduleWriteRate] = useState(0);
  const [loading, setLoading] = useState(true);
  const [anomalyLoading, setAnomalyLoading] = useState(true);
  const [anomalyError, setAnomalyError] = useState("");
  const [error, setError] = useState("");
  const memory = snapshot.history.map(sample => sample.system.ram_percent);
  const swap = snapshot.history.map(sample => sample.system.swap_percent);
  const read = snapshot.history.map(sample => sample.processes.reduce((sum, process) => sum + (process.read_bytes_per_sec ?? 0), 0));
  const write = snapshot.history.map(sample => sample.processes.reduce((sum, process) => sum + (process.write_bytes_per_sec ?? 0), 0));
  const topMemory = [...memoryProcesses].sort((a, b) => b.memory_percent - a.memory_percent).slice(0, 10);
  const observations = [
    memory.length > 1 ? `RAM moved from ${memory[0].toFixed(1)}% to ${memory.at(-1)?.toFixed(1)}% across the retained history.` : "RAM trend requires at least two collected samples.",
    swap.length > 1 ? `Swap is currently ${swap.at(-1)?.toFixed(1)}%; this is a direct system measurement.` : "Swap trend is unavailable until more samples are collected.",
    read.length > 1 ? `Current aggregate read/write rates are ${rate(read.at(-1) ?? 0)} and ${rate(write.at(-1) ?? 0)}.` : "Aggregate I/O trend requires at least two rate samples.",
  ];
  const loadAnomalies = () => {
    setAnomalyLoading(true);
    setAnomalyError("");
    return api<{ items: Anomaly[]; alerts: Record<string, unknown>[] }>("/anomalies")
      .then(response => setAnomalies(response))
      .catch(errorValue => setAnomalyError(errorValue instanceof Error ? errorValue.message : "Unable to load anomaly evidence."))
      .finally(() => setAnomalyLoading(false));
  };
  useEffect(() => {
    let active = true;
    setLoading(true);
    api<{ processes: MemoryProcess[] }>("/system/memory")
      .then(memoryResponse => active && setMemoryProcesses(memoryResponse.processes ?? []))
      .catch(errorValue => active && setError(errorValue instanceof Error ? errorValue.message : "Unable to load system memory."))
      .finally(() => active && setLoading(false));
    loadAnomalies();
    return () => { active = false; };
  }, [snapshot.history.length, snapshot.processes.length]);
  const anomalyRows = (anomalies?.items ?? []).flatMap(item => Object.entries(item)
    .filter(([key, value]) => ["io_spike", "io_stall", "sustained_high_io", "rw_ratio_shift"].includes(key) && Boolean((value as { anomaly?: boolean }).anomaly))
    .map(([type, value]) => ({ item, type, evidence: value as Record<string, unknown> })));
  const generateSchedulingAnalysis = async () => {
    if (scheduleLoading) return;
    const usableMetrics = snapshot.processes.filter(process => process.total_io_bytes_per_sec > 100);
    if (!usableMetrics.length) {
      setSchedule(null);
      setScheduleNotice("More telemetry samples are needed before a synthetic workload can be generated.");
      return;
    }
    try {
      setScheduleLoading(true);
      setScheduleError("");
      setScheduleNotice("");
      const response = await post<unknown>("/scheduling/generate-workload", {
        metrics: usableMetrics,
        initial_head: 0,
        disk_size: 200,
        direction: "right",
      });
      if (!isGeneratedSchedule(response)) throw new Error("The scheduling service returned an invalid analysis.");
      if (!response.requests.length) {
        setScheduleNotice("No usable I/O activity produced a synthetic workload. More telemetry samples are needed.");
        setSchedule(null);
      } else {
        setScheduleProcessCount(usableMetrics.length);
        setScheduleReadRate(usableMetrics.reduce((total, process) => total + (process.read_bytes_per_sec ?? 0), 0));
        setScheduleWriteRate(usableMetrics.reduce((total, process) => total + (process.write_bytes_per_sec ?? 0), 0));
        setSchedule(response.analysis);
      }
    } catch (errorValue) {
      setScheduleError(errorValue instanceof Error ? errorValue.message : "Unable to generate scheduling analysis.");
    } finally {
      setScheduleLoading(false);
    }
  };
  const classifications = [...snapshot.processes].sort((a, b) => b.total_io_bytes_per_sec - a.total_io_bytes_per_sec).slice(0, 12);
  return <div className="page-stack">
    {error && <State error>{error}</State>}
    <section className="metrics compact">
      <Metric label="RAM now" value={`${snapshot.system.ram_percent.toFixed(1)}%`} detail="Directly measured" />
      <Metric label="Swap now" value={`${snapshot.system.swap_percent.toFixed(1)}%`} detail="Directly measured" />
      <Metric label="History samples" value={String(snapshot.history.length)} detail="Bounded collector history" />
    </section>
    <div className="two-col">
      <Panel title="Memory utilization" eyebrow="DIRECTLY MEASURED">{snapshot.history.length > 1 ? <Trend values={memory} second={swap} name="RAM and swap utilization history" /> : <Empty text="Collecting memory history. Two samples are required for a trend." />}<div className="legend"><span className="legend-cpu" />RAM <span className="legend-memory" />Swap</div></Panel>
      <Panel title="Evidence-based observations" eyebrow="CALCULATED FROM HISTORY"><ul className="observation-list">{observations.map(observation => <li key={observation}>{observation}</li>)}</ul></Panel>
    </div>
    <Panel title="Per-process memory usage" eyebrow="CURRENT ACCESSIBLE PROCESSES"><p className="muted">Memory percentage is measured by the collector. RSS is shown only when the operating system permits access.</p>{loading ? <State>Loading memory process data…</State> : <div className="table-wrap"><table><thead><tr><th>Process</th><th>PID</th><th>Memory</th><th>RSS</th><th>Trend samples</th></tr></thead><tbody>{topMemory.map(process => { const history = snapshot.history.flatMap(sample => sample.processes.filter(item => item.pid === process.pid)); return <tr key={process.pid}><td className="process-cell" title={process.name}>{process.name}</td><td>{process.pid}</td><td>{process.memory_percent.toFixed(2)}%</td><td>{process.memory_rss_mb == null ? "Unavailable" : `${process.memory_rss_mb.toFixed(2)} MB`}</td><td>{history.length || "Unavailable"}</td></tr>; })}</tbody></table>{!topMemory.length && <Empty text="No accessible process memory measurements are available." />}</div>}</Panel>
    <Panel title="Behavior classification evidence" eyebrow="INFERENCE FROM MEASURED CPU AND I/O"><p className="muted">Classifications are rule-based inferences, not operating-system labels. The supporting CPU and I/O measurements are shown below.</p><div className="table-wrap"><table><thead><tr><th>Process</th><th>Classification</th><th>CPU</th><th>I/O rate</th><th>Explanation</th></tr></thead><tbody>{classifications.map(process => <tr key={process.pid}><td>{process.name}<small>PID {process.pid}</small></td><td><span className="tag">{process.classification?.classification ?? "Unavailable"}</span></td><td>{process.cpu_percent.toFixed(1)}%</td><td>{rate(process.total_io_bytes_per_sec)}</td><td className="explanation">{process.classification?.reason ?? "Insufficient history for a classification."}</td></tr>)}</tbody></table>{!classifications.length && <Empty text="No classification evidence is available yet." />}</div></Panel>
    <Panel title="Detected anomalies" eyebrow="INFERENCE FROM BASELINES AND THRESHOLDS">{anomalyLoading ? <State>Loading anomaly evidence…</State> : anomalyError ? <div className="state error"><p>{anomalyError}</p><button className="control" onClick={loadAnomalies}>Retry</button></div> : anomalyRows.length ? <div className="table-wrap"><table><thead><tr><th>Process</th><th>Type</th><th>Severity</th><th>Observed</th><th>Baseline</th><th>Thresholds</th></tr></thead><tbody>{anomalyRows.map(({ item, type, evidence }) => <tr key={`${item.pid}-${type}`}><td>{item.name}<small>PID {item.pid}</small></td><td>{type.replaceAll("_", " ")}</td><td><span className={`severity ${String(evidence.severity ?? "unknown")}`}>{String(evidence.severity ?? "UNKNOWN").toUpperCase()}</span></td><td>{String(evidence.current_rate ?? evidence.current_ratio ?? "Unavailable")}</td><td>{String(evidence.baseline_rate ?? evidence.baseline_ratio ?? "Unavailable")}</td><td className="explanation">{JSON.stringify(evidence.thresholds ?? {})}</td></tr>)}</tbody></table></div> : <Empty text="No anomalies detected in the selected period." />}</Panel>
    <Panel title="Observed I/O → scheduling analysis" eyebrow="SIMULATED RESULT"><p className="muted">This uses the existing deterministic mapping from observed process I/O counters to synthetic cylinder requests. It does not measure physical disk requests, latency, or queue depth.</p><button className="primary" disabled={scheduleLoading} onClick={generateSchedulingAnalysis}>{scheduleLoading ? "Generating analysis…" : "Generate analysis from current I/O"}</button>{scheduleError && <div className="state error"><p>{scheduleError}</p><button className="control" onClick={generateSchedulingAnalysis} disabled={scheduleLoading}>Retry</button></div>}{scheduleNotice && <State>{scheduleNotice}</State>}{schedule && <div className="page-stack"><div className="evidence"><span>Processes used: {scheduleProcessCount}</span><span>Read activity: {rate(scheduleReadRate)}</span><span>Write activity: {rate(scheduleWriteRate)}</span><span>Synthetic requests: {schedule.request_count}</span></div><div className="recommendation"><strong>{schedule.recommended_algorithm}</strong><span>{schedule.reason}</span></div><div className="schedule-grid">{Object.entries(schedule.results).map(([name, result]) => <article className="schedule-card" key={name}><h3>{name}</h3><strong>{result.total_head_movement} simulated cylinders</strong><span>{result.average_seek_distance.toFixed(2)} average movement/request</span><p className="muted">Service sequence</p><div className="sequence">{result.request_order.map((request, index) => <span key={`${request}-${index}`}>{request}</span>)}</div></article>)}</div><p className="muted">These deterministic results compare algorithms against a synthetic workload only. They are not physical disk positions, latency, queue depth, or a prediction of hardware performance.</p></div>}</Panel>
  </div>;
}

function Lab() {
  const [tab, setTab] = useState("pages"); const [pageText, setPageText] = useState("1,2,3,1,4,2,5"); const [frames, setFrames] = useState(3); const [results, setResults] = useState<Record<string, { page_faults: number; page_hits: number; fault_rate: number }> | null>(null); const [allocText, setAllocText] = useState("requested,block_size\n250,256\n400,512"); const [alloc, setAlloc] = useState<Record<string, unknown> | null>(null); const [memory, setMemory] = useState(1024); const [blocks, setBlocks] = useState("0,256,true\n256,128,false\n384,640,true"); const [external, setExternal] = useState<Record<string, unknown> | null>(null); const [error, setError] = useState("");
  const run = async (task: () => Promise<unknown>) => { try { setError(""); await task(); } catch (e) { setError(e instanceof Error ? e.message : "Invalid lab input"); } };
  return <div className="page-stack"><div className="tabs" role="tablist">{[["pages", "Page replacement"], ["internal", "Internal fragmentation"], ["external", "External fragmentation"], ["cpu", "CPU scheduling"], ["deadlock", "Deadlock"]].map(([id, label]) => <button role="tab" aria-selected={tab === id} className={tab === id ? "tab active" : "tab"} onClick={() => setTab(id)} key={id}>{label}</button>)}</div>{error && <p className="error">{error}</p>}{tab === "cpu" ? <CpuSchedulingLab /> : tab === "deadlock" ? <DeadlockLab /> : tab === "pages" && <Panel title="Page replacement" eyebrow="OS LAB · SIMULATION"><div className="form-grid"><label>Reference string<textarea value={pageText} onChange={e => setPageText(e.target.value)} /></label><label>Frames<input type="number" min="1" value={frames} onChange={e => setFrames(Number(e.target.value))} /></label></div><button className="primary" onClick={() => run(async () => setResults((await post<{ results: typeof results }>("/os-lab/page-replacement", { pages: pageText.split(",").map(Number), frames, algorithm: "ALL" })).results))}>Run comparison</button>{results && <div className="result-grid">{Object.entries(results).map(([name, result]) => <article className="result-card" key={name}><h3>{name}</h3><strong>{result.page_faults} faults</strong><span>{result.page_hits} hits · {(result.fault_rate * 100).toFixed(1)}% fault rate</span></article>)}</div>}</Panel>}{tab === "internal" && <Panel title="Internal fragmentation" eyebrow="OS LAB · SIMULATION"><p className="muted">CSV format: requested,block_size.</p><textarea value={allocText} onChange={e => setAllocText(e.target.value)} /><button className="primary" onClick={() => run(async () => setAlloc(await post("/os-lab/fragmentation/internal", { allocations: allocText.trim().split("\n").slice(1).map(row => { const [requested, block_size] = row.split(",").map(Number); return { requested, block_size }; }) })))}>Calculate</button>{alloc && <div className="result-grid"><Metric label="Wasted memory" value={String(alloc.wasted_memory)} /><Metric label="Fragmentation" value={`${alloc.fragmentation_percentage}%`} /></div>}</Panel>}{tab === "external" && <Panel title="External fragmentation" eyebrow="OS LAB · SIMULATION"><label>Total memory<input type="number" min="1" value={memory} onChange={e => setMemory(Number(e.target.value))} /></label><p className="muted">CSV format: start,size,allocated.</p><textarea value={blocks} onChange={e => setBlocks(e.target.value)} /><button className="primary" onClick={() => run(async () => setExternal(await post("/os-lab/fragmentation/external", { total_memory: memory, blocks: blocks.trim().split("\n").map(row => { const [start, size, allocated] = row.split(","); return { start: Number(start), size: Number(size), allocated: allocated.trim().toLowerCase() === "true" }; }) })))}>Calculate</button>{external && <div className="result-grid"><Metric label="Free memory" value={String(external.free_memory)} /><Metric label="Largest free block" value={String(external.largest_free_block)} /><Metric label="Fragmentation" value={`${external.fragmentation_percentage}%`} /></div>}</Panel>}</div>;
}

function SettingsPage({ paused, setPaused, snapshot }: { paused: boolean; setPaused: (v: boolean) => void; snapshot: Snapshot }) {
  const [settings, setSettings] = useState<Settings | null>(null); const [message, setMessage] = useState("");
  useEffect(() => { api<Settings>("/settings").then(setSettings).catch(e => setMessage(e.message)); }, []);
  const save = async () => { if (!settings) return; try { setSettings(await api<Settings>("/settings", { method: "PUT", body: JSON.stringify(settings) })); setMessage("Settings saved."); } catch (e) { setMessage(e instanceof Error ? e.message : "Unable to save settings."); } };
  return <div className="page-stack"><Panel title="Monitoring settings" eyebrow="LOCAL CONFIGURATION">{settings ? <div className="form-grid"><label>Refresh interval (seconds)<input type="number" min=".5" max="60" step=".5" value={settings.refresh_interval} onChange={e => setSettings({ ...settings, refresh_interval: Number(e.target.value) })} /></label><label>History window<input type="number" min="5" max="600" value={settings.history_window} onChange={e => setSettings({ ...settings, history_window: Number(e.target.value) })} /></label><label>CPU threshold (%)<input type="number" min=".1" value={settings.cpu_threshold} onChange={e => setSettings({ ...settings, cpu_threshold: Number(e.target.value) })} /></label><label>I/O threshold (bytes/s)<input type="number" min="1" value={settings.io_threshold} onChange={e => setSettings({ ...settings, io_threshold: Number(e.target.value) })} /></label></div> : <State>Loading settings…</State>}<div className="button-row"><button className="primary" onClick={save}>Save settings</button><button className="control" onClick={() => setPaused(!paused)}>{paused ? "Resume collection" : "Pause collection"}</button></div>{message && <p className="muted">{message}</p>}</Panel><Panel title="Reports & exports" eyebrow="OBSERVED TELEMETRY"><p className="muted">JSON and CSV exports include available local telemetry. Scheduling results are simulations and are not mixed with observed process data.</p><div className="button-row"><a className="primary link-button" href={`${API}/export?format=json`} download>Download JSON</a><a className="primary link-button" href={`${API}/export?format=csv`} download>Download CSV</a></div></Panel><Panel title="Backend status"><div className="detail-grid"><div><span className="detail-label">Collector</span><strong>{snapshot.collection_status}</strong></div><div><span className="detail-label">Data policy</span><strong>Local-only / read-only</strong></div><div><span className="detail-label">History samples</span><strong>{snapshot.history.length}</strong></div></div></Panel></div>;
}

function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null); const [error, setError] = useState(""); const [paused, setPaused] = useState(false);
  useEffect(() => { if (paused) return; let active = true; const load = () => api<Snapshot>("/system/summary").then(value => { if (active) { setSnapshot(value); setError(""); } }).catch(e => active && setError(e.message)); load(); const timer = window.setInterval(load, 2000); return () => { active = false; window.clearInterval(timer); }; }, [paused]);
  const content = snapshot ? <Routes><Route path="/" element={<Overview snapshot={snapshot} />} /><Route path="/processes" element={<ProcessExplorer snapshot={snapshot} />} /><Route path="/processes/:pid" element={<ProcessDetail snapshot={snapshot} />} /><Route path="/analytics" element={<Analytics snapshot={snapshot} />} /><Route path="/anomalies" element={<Anomalies />} /><Route path="/scheduling" element={<Scheduling snapshot={snapshot} />} /><Route path="/lab" element={<SystemIntelligence snapshot={snapshot} />} /><Route path="/settings" element={<SettingsPage paused={paused} setPaused={setPaused} snapshot={snapshot} />} /><Route path="*" element={<Overview snapshot={snapshot} />} /></Routes> : <State error={Boolean(error)}>{error ? `Backend unavailable: ${error}` : "Connecting to the local collector…"}</State>;
  return <Layout paused={paused} setPaused={setPaused} snapshot={snapshot}>{content}</Layout>;
}
createRoot(document.getElementById("root")!).render(<StrictMode><BrowserRouter><App /></BrowserRouter></StrictMode>);
