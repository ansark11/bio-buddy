"use client";

import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";

const QUICK_SUPPLEMENTS = ["Vitamin D3", "Fish Oil", "Magnesium", "Creatine", "Vitamin B12"];

const STEPS = [
  { question: "What's your weight today?" },
  { question: "How's your energy?" },
  { question: "How much water today?" },
  { question: "Any supplements today?" },
];

function todayKey() {
  return `quick_log_done_${new Date().toISOString().slice(0, 10)}`;
}

export default function QuickLogCard() {
  const [done, setDone] = useState(false);
  useEffect(() => {
    setDone(!!localStorage.getItem(todayKey()));
  }, []);
  const [step, setStep] = useState(0);
  const [weight, setWeight] = useState("");
  const [energy, setEnergy] = useState<number | null>(null);
  const [water, setWater] = useState("");
  const [supps, setSupps] = useState<Record<string, boolean>>(
    Object.fromEntries(QUICK_SUPPLEMENTS.map((s) => [s, false]))
  );
  const [customSupp, setCustomSupp] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function advance() {
    if (step < STEPS.length - 1) setStep((s) => s + 1);
  }

  function canAdvance() {
    if (step === 0) return weight !== "";
    if (step === 2) return water !== "";
    return true;
  }

  async function save() {
    setSaving(true);
    setError("");
    const today = new Date().toISOString();
    const calls: Promise<unknown>[] = [];

    if (weight) calls.push(apiClient.post("/api/metrics/log", {
      metric_name: "weight_kg", metric_value: parseFloat(weight),
      unit: "kg", category: "body_composition", recorded_at: today,
    }));
    if (energy !== null) calls.push(apiClient.post("/api/metrics/log", {
      metric_name: "energy_rating", metric_value: energy,
      unit: "rating", category: "subjective", recorded_at: today,
    }));
    if (water) calls.push(apiClient.post("/api/metrics/log", {
      metric_name: "water_glasses", metric_value: parseFloat(water),
      unit: "glasses", category: "nutrition", recorded_at: today,
    }));

    const allSupps = { ...supps };
    if (customSupp.trim()) allSupps[customSupp.trim()] = true;
    for (const [name, taken] of Object.entries(allSupps)) {
      if (taken) calls.push(apiClient.post("/api/metrics/log/supplement", {
        supplement_name: name, taken: true,
        recorded_at: new Date().toISOString().slice(0, 10),
      }));
    }

    try {
      await Promise.all(calls);
      localStorage.setItem(todayKey(), "1");
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  if (done) {
    return (
      <div className="bg-card rounded-xl border border-white/[0.08] px-5 py-3 flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-ok shrink-0" />
        <span className="text-sm text-muted">Today's log saved</span>
        <button
          onClick={() => { setDone(false); setStep(0); }}
          className="ml-auto text-[11px] text-muted hover:text-ink transition-colors"
        >
          Edit
        </button>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl border border-white/[0.08] px-5 py-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-[10px] font-semibold text-muted uppercase tracking-widest">Today's Log</span>
        <div className="flex gap-1 ml-1">
          {STEPS.map((_, i) => (
            <button
              key={i}
              onClick={() => setStep(i)}
              className={`w-1.5 h-1.5 rounded-full transition-colors ${i === step ? "bg-hblue" : "bg-white/20"}`}
            />
          ))}
        </div>
        {error && <span className="text-bad text-xs ml-auto">{error}</span>}
      </div>

      {/* Step content */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm text-ink/80 shrink-0 w-52">{STEPS[step].question}</span>

        {step === 0 && (
          <div className="flex items-center gap-2 flex-1">
            <input
              type="number" step="0.1"
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && canAdvance() && advance()}
              autoFocus
              className="w-24 bg-page border border-white/[0.08] rounded-lg px-3 py-1.5 text-sm text-ink outline-none focus:border-hblue/40"
            />
            <span className="text-xs text-muted">kg</span>
          </div>
        )}

        {step === 1 && (
          <div className="flex items-center gap-2 flex-1 flex-wrap">
            <div className="flex gap-1.5">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => { setEnergy(n); setTimeout(advance, 150); }}
                  className={`w-8 h-8 rounded-lg text-xs font-medium transition-colors ${
                    energy === n ? "bg-hblue text-white" : "bg-page border border-white/[0.08] text-muted hover:border-hblue/40"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
            <span className="text-[10px] text-muted">1 = exhausted · 5 = great</span>
          </div>
        )}

        {step === 2 && (
          <div className="flex items-center gap-2 flex-1">
            <input
              type="number" step="1"
              value={water}
              onChange={(e) => setWater(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && canAdvance() && advance()}
              autoFocus
              className="w-24 bg-page border border-white/[0.08] rounded-lg px-3 py-1.5 text-sm text-ink outline-none focus:border-hblue/40"
            />
            <span className="text-xs text-muted">glasses</span>
          </div>
        )}

        {step === 3 && (
          <div className="flex flex-col gap-2 flex-1">
            <div className="flex gap-1.5 flex-wrap">
              {QUICK_SUPPLEMENTS.map((s) => (
                <button
                  key={s}
                  onClick={() => setSupps((prev) => ({ ...prev, [s]: !prev[s] }))}
                  className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                    supps[s]
                      ? "border-hblue/50 bg-hblue/10 text-hblue"
                      : "border-white/[0.08] text-muted hover:border-white/20"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={customSupp}
              onChange={(e) => setCustomSupp(e.target.value)}
              placeholder="Other supplement…"
              className="w-48 bg-page border border-white/[0.08] rounded-lg px-3 py-1.5 text-sm text-ink placeholder-muted outline-none focus:border-hblue/40"
            />
          </div>
        )}

        {/* Navigation */}
        <div className="shrink-0 ml-auto self-start">
          {step < STEPS.length - 1 ? (
            <button
              onClick={advance}
              disabled={!canAdvance()}
              className="w-8 h-8 rounded-lg bg-page border border-white/[0.08] flex items-center justify-center text-muted hover:border-hblue/40 hover:text-ink disabled:opacity-30 transition-colors"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 6h8M6 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          ) : (
            <button
              onClick={save}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg bg-hblue text-white text-xs font-medium hover:bg-hblue/80 disabled:opacity-50 transition-colors"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
