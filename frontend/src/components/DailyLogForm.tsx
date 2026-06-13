"use client";

import { useState } from "react";
import { apiClient } from "@/lib/api";

const DEFAULT_SUPPLEMENTS = ["Vitamin D3", "Fish Oil", "Magnesium", "Creatine", "Vitamin B12"];

export default function DailyLogForm() {
  const today = new Date().toISOString().slice(0, 10);
  const [weight, setWeight] = useState("");
  const [energy, setEnergy] = useState<number | null>(null);
  const [water, setWater] = useState("");
  const [supplements, setSupplements] = useState<Record<string, boolean>>(
    Object.fromEntries(DEFAULT_SUPPLEMENTS.map((s) => [s, false]))
  );
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    setSubmitting(true);
    setError("");
    setSuccess(false);
    const promises: Promise<unknown>[] = [];

    if (weight) {
      promises.push(
        apiClient.post("/api/metrics/log", {
          metric_name: "weight_kg",
          metric_value: parseFloat(weight),
          unit: "kg",
          category: "body_composition",
          recorded_at: new Date().toISOString(),
        })
      );
    }

    if (energy !== null) {
      promises.push(
        apiClient.post("/api/metrics/log", {
          metric_name: "energy_rating",
          metric_value: energy,
          unit: "rating",
          category: "subjective",
          recorded_at: new Date().toISOString(),
        })
      );
    }

    if (water) {
      promises.push(
        apiClient.post("/api/metrics/log", {
          metric_name: "water_glasses",
          metric_value: parseFloat(water),
          unit: "glasses",
          category: "nutrition",
          recorded_at: new Date().toISOString(),
        })
      );
    }

    for (const [name, taken] of Object.entries(supplements)) {
      if (taken) {
        promises.push(
          apiClient.post("/api/metrics/log/supplement", {
            supplement_name: name,
            taken: true,
            recorded_at: today,
          })
        );
      }
    }

    try {
      await Promise.all(promises);
      setSuccess(true);
      setWeight("");
      setEnergy(null);
      setWater("");
      setSupplements(Object.fromEntries(DEFAULT_SUPPLEMENTS.map((s) => [s, false])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <h2 className="font-semibold">Body Weight</h2>
        <div className="flex items-center gap-3">
          <input
            type="number"
            step="0.1"
            placeholder="e.g. 82.5"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span className="text-gray-500 text-sm">kg</span>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
        <h2 className="font-semibold">Energy Level</h2>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => setEnergy(n)}
              className={`w-10 h-10 rounded-lg text-sm font-medium transition-colors ${
                energy === n ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-400">1 = exhausted, 5 = great</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
        <h2 className="font-semibold">Water Intake</h2>
        <div className="flex items-center gap-3">
          <input
            type="number"
            step="1"
            placeholder="e.g. 8"
            value={water}
            onChange={(e) => setWater(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-28 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span className="text-gray-500 text-sm">glasses</span>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
        <h2 className="font-semibold">Supplements</h2>
        <div className="grid grid-cols-2 gap-2">
          {DEFAULT_SUPPLEMENTS.map((s) => (
            <button
              key={s}
              onClick={() => setSupplements((prev) => ({ ...prev, [s]: !prev[s] }))}
              className={`text-sm px-3 py-2 rounded-lg border transition-colors text-left ${
                supplements[s]
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {supplements[s] ? "✓ " : ""}{s}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}
      {success && <p className="text-green-600 text-sm">Saved successfully!</p>}

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="w-full bg-blue-600 text-white rounded-lg py-2.5 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        {submitting ? "Saving..." : "Save Today's Log"}
      </button>
    </div>
  );
}
