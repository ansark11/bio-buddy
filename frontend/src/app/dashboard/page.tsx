"use client";

import { useState, useEffect } from "react";
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import Navbar from "@/components/Navbar";
import MetricChart from "@/components/MetricChart";
import BiomarkerTable from "@/components/BiomarkerTable";
import ChatWindow from "@/components/ChatWindow";
import QuickLogCard from "@/components/QuickLogCard";
import { apiClient } from "@/lib/api";
import type { HealthMetric, TimeSeriesPoint, CorrelateResult, Document } from "@/lib/types";

const CORRELATABLE_METRICS = [
  { name: "sleep_duration_hours", label: "Sleep Duration" },
  { name: "resting_heart_rate", label: "Resting Heart Rate" },
  { name: "hrv", label: "HRV" },
  { name: "weight_kg", label: "Weight" },
  { name: "step_count", label: "Steps" },
  { name: "active_calories", label: "Active Calories" },
  { name: "exercise_minutes", label: "Exercise Minutes" },
  { name: "daily_calories", label: "Daily Calories" },
  { name: "daily_protein_g", label: "Protein (g)" },
  { name: "daily_carbs_g", label: "Carbs (g)" },
  { name: "daily_fat_g", label: "Fat (g)" },
  { name: "daily_sodium_mg", label: "Sodium (mg)" },
];

function corrLabel(r: number | null): string {
  if (r === null) return "insufficient data";
  const abs = Math.abs(r);
  const dir = r > 0 ? "positive" : "negative";
  if (abs >= 0.7) return `strong ${dir}`;
  if (abs >= 0.4) return `moderate ${dir}`;
  if (abs >= 0.2) return `weak ${dir}`;
  return "no correlation";
}

const SUMMARY_METRICS = [
  { name: "weight_kg",            label: "Weight",     unit: "kg",  color: "#60A5FA" },
  { name: "resting_heart_rate",   label: "Resting HR", unit: "bpm", color: "#F87171" },
  { name: "hrv",                  label: "HRV",        unit: "ms",  color: "#4ADE80" },
  { name: "sleep_duration_hours", label: "Sleep",      unit: "h",   color: "#FBBF24" },
  { name: "daily_calories",       label: "Calories",   unit: "cal", color: "#8FA3BF" },
];

const NUTRITION_COLS = [
  { key: "daily_calories",      label: "Calories",  unit: "cal" },
  { key: "daily_protein_g",     label: "Protein",   unit: "g" },
  { key: "daily_carbs_g",       label: "Carbs",     unit: "g" },
  { key: "daily_fat_g",         label: "Fat",       unit: "g" },
  { key: "daily_sodium_mg",     label: "Sodium",    unit: "mg" },
  { key: "daily_fiber_g",       label: "Fiber",     unit: "g" },
];

const FITNESS_COLS = [
  { key: "step_count",            label: "Steps",      unit: "" },
  { key: "active_calories",       label: "Active Cal", unit: "kcal" },
  { key: "exercise_minutes",      label: "Exercise",   unit: "min" },
  { key: "resting_heart_rate",    label: "Resting HR", unit: "bpm" },
  { key: "hrv",                   label: "HRV",        unit: "ms" },
  { key: "sleep_duration_hours",  label: "Sleep",      unit: "h" },
];

type SummaryEntry = { value: number; unit: string; recorded_at: string };

export default function DashboardPage() {
  const [summary, setSummary] = useState<Record<string, SummaryEntry>>({});
  const [charts, setCharts] = useState<Record<string, TimeSeriesPoint[]>>({});
  const [activeChart, setActiveChart] = useState("weight_kg");
  const [dateRange, setDateRange] = useState("30");

  const [corrMetricA, setCorrMetricA] = useState("sleep_duration_hours");
  const [corrMetricB, setCorrMetricB] = useState("daily_calories");
  const [corrResult, setCorrResult] = useState<CorrelateResult | null>(null);
  const [corrLoading, setCorrLoading] = useState(false);

  const [rawTab, setRawTab] = useState<"blood_test" | "nutrition" | "fitness">("blood_test");

  const [bloodTestDocs, setBloodTestDocs] = useState<Document[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [docBiomarkers, setDocBiomarkers] = useState<HealthMetric[]>([]);

  const [nutritionDays, setNutritionDays] = useState(90);
  const [nutritionRows, setNutritionRows] = useState<HealthMetric[]>([]);
  const [nutritionHasMore, setNutritionHasMore] = useState(false);

  const [fitnessDays, setFitnessDays] = useState(90);
  const [fitnessRows, setFitnessRows] = useState<HealthMetric[]>([]);
  const [fitnessHasMore, setFitnessHasMore] = useState(false);

  useEffect(() => {
    apiClient.get<{ summary: Record<string, SummaryEntry> }>("/api/metrics/summary")
      .then((d) => setSummary(d.summary))
      .catch(() => {});
    apiClient.get<{ documents: Document[] }>("/api/ingest/documents")
      .then((d) => {
        const docs = d.documents.filter((doc) => doc.source === "blood_test");
        setBloodTestDocs(docs);
        if (docs.length === 1) setSelectedDocId(docs[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const end = new Date().toISOString().slice(0, 10);
    const start = new Date(Date.now() - parseInt(dateRange) * 86400000).toISOString().slice(0, 10);
    apiClient
      .get<{ data: TimeSeriesPoint[] }>(`/api/metrics/timeseries?metric_name=${activeChart}&start_date=${start}&end_date=${end}`)
      .then((d) => setCharts((prev) => ({ ...prev, [activeChart]: d.data })))
      .catch(() => {});
  }, [activeChart, dateRange]);

  useEffect(() => {
    if (corrMetricA === corrMetricB) return;
    setCorrLoading(true);
    apiClient
      .get<CorrelateResult>(`/api/metrics/correlate?metric_a=${corrMetricA}&metric_b=${corrMetricB}`)
      .then((d) => setCorrResult(d))
      .catch(() => {})
      .finally(() => setCorrLoading(false));
  }, [corrMetricA, corrMetricB]);

  useEffect(() => {
    if (!selectedDocId) { setDocBiomarkers([]); return; }
    apiClient
      .get<{ metrics: HealthMetric[] }>(`/api/metrics?document_id=${selectedDocId}`)
      .then((d) => {
        if (d.metrics.length > 0) {
          setDocBiomarkers(d.metrics);
        } else {
          return apiClient
            .get<{ biomarkers: HealthMetric[] }>("/api/metrics/biomarkers/latest")
            .then((b) => setDocBiomarkers(b.biomarkers));
        }
      })
      .catch(() => {});
  }, [selectedDocId]);

  useEffect(() => {
    const start = new Date(Date.now() - nutritionDays * 86400000).toISOString().slice(0, 10);
    apiClient
      .get<{ metrics: HealthMetric[] }>(`/api/metrics?category=nutrition&start_date=${start}`)
      .then((d) => { setNutritionRows(d.metrics); setNutritionHasMore(d.metrics.length >= 500); })
      .catch(() => {});
  }, [nutritionDays]);

  useEffect(() => {
    const start = new Date(Date.now() - fitnessDays * 86400000).toISOString().slice(0, 10);
    Promise.all([
      apiClient.get<{ metrics: HealthMetric[] }>(`/api/metrics?category=activity&start_date=${start}`),
      apiClient.get<{ metrics: HealthMetric[] }>(`/api/metrics?category=cardiovascular&start_date=${start}`),
      apiClient.get<{ metrics: HealthMetric[] }>(`/api/metrics?category=sleep&start_date=${start}`),
    ]).then(([act, cardio, slp]) => {
      setFitnessRows([...act.metrics, ...cardio.metrics, ...slp.metrics]);
      setFitnessHasMore(act.metrics.length >= 500 || cardio.metrics.length >= 500 || slp.metrics.length >= 500);
    }).catch(() => {});
  }, [fitnessDays]);

  const nutritionByDate = nutritionRows.reduce((acc, r) => {
    const d = r.recorded_at.slice(0, 10);
    if (!acc[d]) acc[d] = {};
    acc[d][r.metric_name] = r.metric_value;
    return acc;
  }, {} as Record<string, Record<string, number>>);
  const nutritionPivoted = Object.entries(nutritionByDate).sort(([a], [b]) => b.localeCompare(a));

  const fitnessByDate = fitnessRows.reduce((acc, r) => {
    const d = r.recorded_at.slice(0, 10);
    if (!acc[d]) acc[d] = {};
    acc[d][r.metric_name] = r.metric_value;
    return acc;
  }, {} as Record<string, Record<string, number>>);
  const fitnessPivoted = Object.entries(fitnessByDate).sort(([a], [b]) => b.localeCompare(a));

  const currentChart = SUMMARY_METRICS.find((m) => m.name === activeChart);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">

        {/* LEFT: scrollable dashboard */}
        <main className="flex-1 overflow-y-auto px-6 py-5 space-y-4 min-w-0">

          <QuickLogCard />

          {/* Latest Metrics */}
          <div className="bg-card rounded-xl border border-white/[0.08] p-5">
            <p className="text-[11px] font-semibold text-muted uppercase tracking-widest mb-3">Latest Metrics</p>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              {SUMMARY_METRICS.map((m) => {
                const entry = summary[m.name];
                return (
                  <div key={m.name} className="bg-page rounded-lg p-3">
                    <p className="text-[11px] text-muted font-medium uppercase tracking-wide">{m.label}</p>
                    <p className="text-xl font-heading font-bold mt-1" style={{ color: m.color }}>
                      {entry ? `${entry.value}` : "—"}
                    </p>
                    <p className="text-xs text-muted">{m.unit}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Trend Chart */}
          <div className="bg-card rounded-xl border border-white/[0.08] p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <div className="flex gap-1.5 flex-wrap">
                {SUMMARY_METRICS.map((m) => (
                  <button
                    key={m.name}
                    onClick={() => setActiveChart(m.name)}
                    className={`text-xs px-3 py-1.5 rounded-lg transition-colors font-medium ${
                      activeChart === m.name
                        ? "bg-hblue text-page"
                        : "bg-cardhi text-muted hover:text-ink"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              <div className="flex gap-1">
                {["7", "30", "90", "180", "365"].map((d) => (
                  <button
                    key={d}
                    onClick={() => setDateRange(d)}
                    className={`text-xs px-2 py-1 rounded transition-colors ${
                      dateRange === d ? "bg-ink text-page font-medium" : "text-muted hover:text-ink"
                    }`}
                  >
                    {d === "365" ? "1Y" : d === "180" ? "6M" : d === "90" ? "3M" : d === "30" ? "1M" : "1W"}
                  </button>
                ))}
              </div>
            </div>
            <MetricChart
              data={charts[activeChart] ?? []}
              metricName={currentChart?.label ?? activeChart}
              unit={currentChart?.unit}
              color={currentChart?.color}
            />
          </div>

          {/* Raw Data */}
          <div className="bg-card rounded-xl border border-white/[0.08] p-5 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold text-muted uppercase tracking-widest">Raw Data</p>
              <div className="flex gap-1">
                {(["blood_test", "nutrition", "fitness"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setRawTab(tab)}
                    className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                      rawTab === tab ? "bg-hblue text-page" : "bg-cardhi text-muted hover:text-ink"
                    }`}
                  >
                    {tab === "blood_test" ? "Blood Test" : tab === "nutrition" ? "Nutrition" : "Fitness"}
                  </button>
                ))}
              </div>
            </div>

            {/* Blood Test tab */}
            {rawTab === "blood_test" && (
              bloodTestDocs.length === 0 ? (
                <p className="text-sm text-muted">No blood test reports uploaded yet.</p>
              ) : (
                <div className="space-y-4">
                  {bloodTestDocs.length > 1 && (
                    <select
                      value={selectedDocId}
                      onChange={(e) => setSelectedDocId(e.target.value)}
                      className="bg-page border border-white/[0.08] text-ink rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-hblue/40"
                    >
                      <option value="">Select a report…</option>
                      {bloodTestDocs.map((doc) => (
                        <option key={doc.id} value={doc.id}>
                          {doc.metadata?.lab_name ?? doc.filename} — {doc.metadata?.test_date ?? doc.upload_date.slice(0, 10)}
                        </option>
                      ))}
                    </select>
                  )}
                  {selectedDocId && docBiomarkers.length > 0 && <BiomarkerTable biomarkers={docBiomarkers} />}
                  {selectedDocId && docBiomarkers.length === 0 && (
                    <p className="text-sm text-muted">No biomarker data found for this report.</p>
                  )}
                </div>
              )
            )}

            {/* Nutrition tab */}
            {rawTab === "nutrition" && (
              nutritionPivoted.length === 0 ? (
                <p className="text-sm text-muted">No nutrition data uploaded yet.</p>
              ) : (
                <div className="space-y-3">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-white/[0.08]">
                          <th className="text-left py-2 pr-4 text-[11px] font-semibold text-muted uppercase tracking-wide">Date</th>
                          {NUTRITION_COLS.map((col) => (
                            <th key={col.key} className="text-right py-2 px-2 text-[11px] font-semibold text-muted uppercase tracking-wide whitespace-nowrap">
                              {col.label}{col.unit ? ` (${col.unit})` : ""}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {nutritionPivoted.map(([date, vals]) => (
                          <tr key={date} className="border-b border-white/[0.05] hover:bg-cardhi transition-colors">
                            <td className="py-2 pr-4 text-muted font-medium text-xs">{date}</td>
                            {NUTRITION_COLS.map((col) => (
                              <td key={col.key} className="py-2 px-2 text-right text-ink/80 text-xs">
                                {vals[col.key] !== undefined ? vals[col.key].toLocaleString() : "—"}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {nutritionHasMore && (
                    <button
                      onClick={() => setNutritionDays((d) => d + 90)}
                      className="text-xs text-hblue hover:text-hblue/70 font-medium"
                    >
                      Load earlier data
                    </button>
                  )}
                </div>
              )
            )}

            {/* Fitness tab */}
            {rawTab === "fitness" && (
              fitnessPivoted.length === 0 ? (
                <p className="text-sm text-muted">No fitness data uploaded yet.</p>
              ) : (
                <div className="space-y-3">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-white/[0.08]">
                          <th className="text-left py-2 pr-4 text-[11px] font-semibold text-muted uppercase tracking-wide">Date</th>
                          {FITNESS_COLS.map((col) => (
                            <th key={col.key} className="text-right py-2 px-2 text-[11px] font-semibold text-muted uppercase tracking-wide whitespace-nowrap">
                              {col.label}{col.unit ? ` (${col.unit})` : ""}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {fitnessPivoted.map(([date, vals]) => (
                          <tr key={date} className="border-b border-white/[0.05] hover:bg-cardhi transition-colors">
                            <td className="py-2 pr-4 text-muted font-medium text-xs">{date}</td>
                            {FITNESS_COLS.map((col) => (
                              <td key={col.key} className="py-2 px-2 text-right text-ink/80 text-xs">
                                {vals[col.key] !== undefined ? vals[col.key].toLocaleString() : "—"}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {fitnessHasMore && (
                    <button
                      onClick={() => setFitnessDays((d) => d + 90)}
                      className="text-xs text-hblue hover:text-hblue/70 font-medium"
                    >
                      Load earlier data
                    </button>
                  )}
                </div>
              )
            )}
          </div>

          {/* Correlation Explorer */}
          <div className="bg-card rounded-xl border border-white/[0.08] p-5 space-y-4">
            <p className="text-[11px] font-semibold text-muted uppercase tracking-widest">Correlation Explorer</p>
            <div className="flex items-center gap-3 flex-wrap">
              <select
                value={corrMetricA}
                onChange={(e) => setCorrMetricA(e.target.value)}
                className="bg-page border border-white/[0.08] text-ink rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-hblue/40"
              >
                {CORRELATABLE_METRICS.map((m) => (
                  <option key={m.name} value={m.name}>{m.label}</option>
                ))}
              </select>
              <span className="text-muted text-sm">vs</span>
              <select
                value={corrMetricB}
                onChange={(e) => setCorrMetricB(e.target.value)}
                className="bg-page border border-white/[0.08] text-ink rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-hblue/40"
              >
                {CORRELATABLE_METRICS.map((m) => (
                  <option key={m.name} value={m.name}>{m.label}</option>
                ))}
              </select>
            </div>

            {corrMetricA === corrMetricB && (
              <p className="text-sm text-muted">Select two different metrics to compare.</p>
            )}
            {corrLoading && <p className="text-sm text-muted">Loading…</p>}

            {!corrLoading && corrResult && corrMetricA !== corrMetricB && (
              corrResult.n < 3 ? (
                <p className="text-sm text-muted">Not enough overlapping data for these metrics.</p>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={280}>
                    <ScatterChart margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                      <XAxis
                        dataKey="x"
                        type="number"
                        domain={["auto", "auto"]}
                        name={CORRELATABLE_METRICS.find((m) => m.name === corrMetricA)?.label ?? corrMetricA}
                        tick={{ fontSize: 11, fill: "#8FA3BF" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        dataKey="y"
                        type="number"
                        domain={["auto", "auto"]}
                        name={CORRELATABLE_METRICS.find((m) => m.name === corrMetricB)?.label ?? corrMetricB}
                        tick={{ fontSize: 11, fill: "#8FA3BF" }}
                        axisLine={false}
                        tickLine={false}
                        width={48}
                      />
                      <Tooltip
                        cursor={{ strokeDasharray: "3 3", stroke: "rgba(255,255,255,0.1)" }}
                        contentStyle={{
                          fontSize: 12,
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: 8,
                          background: "#112240",
                          color: "#E8F0FE",
                        }}
                      />
                      <Scatter
                        data={corrResult.data.map((d) => ({ x: d.a_value, y: d.b_value }))}
                        fill="#60A5FA"
                        fillOpacity={0.6}
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                  <p className="text-sm text-muted text-center">
                    r = <strong className="text-ink">{corrResult.correlation ?? "—"}</strong>
                    {" · "}
                    {corrResult.n} data points
                    {" · "}
                    <span className="text-muted/70">{corrLabel(corrResult.correlation)}</span>
                  </p>
                </>
              )
            )}
          </div>
        </main>

        {/* RIGHT: chat panel */}
        <aside className="w-[400px] shrink-0 border-l border-white/[0.08] flex flex-col bg-card">
          <div className="px-4 py-3.5 border-b border-white/[0.08]">
            <h2 className="font-heading font-semibold text-sm text-ink">Ask your data</h2>
          </div>
          <div className="flex-1 overflow-hidden">
            <ChatWindow />
          </div>
        </aside>

      </div>
    </div>
  );
}
