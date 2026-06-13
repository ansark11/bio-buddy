"use client";

import { useState, useEffect, useCallback } from "react";
import { fetchInsights } from "@/lib/api";

function timeAgo(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function InsightText({ text }: { text: string }) {
  const lines = text.split("\n").filter((l) => l.trim());
  return (
    <ul className="space-y-2">
      {lines.map((line, i) => {
        const clean = line.replace(/^[\-\*\•]\s*/, "").replace(/^\d+\.\s*/, "");
        return (
          <li key={i} className="flex gap-2 text-sm text-gray-700 leading-relaxed">
            <span className="mt-1 shrink-0 w-1.5 h-1.5 rounded-full bg-blue-400" />
            <span>{clean}</span>
          </li>
        );
      })}
    </ul>
  );
}

export default function InsightCard() {
  const [insight, setInsight] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchInsights()
      .then((d) => {
        setInsight(d.insight);
        setGeneratedAt(d.generated_at);
      })
      .catch(() => setError("Could not generate insights. Make sure you have uploaded health data."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="bg-white rounded-xl border border-blue-100 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-blue-500 text-lg">✦</span>
          <h2 className="text-sm font-semibold text-gray-700">AI Health Summary</h2>
        </div>
        <div className="flex items-center gap-3">
          {generatedAt && !loading && (
            <span className="text-xs text-gray-400">{timeAgo(generatedAt)}</span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Generating…" : "Refresh"}
          </button>
        </div>
      </div>

      {loading && (
        <div className="space-y-2.5 animate-pulse">
          <div className="h-3.5 bg-gray-100 rounded w-full" />
          <div className="h-3.5 bg-gray-100 rounded w-5/6" />
          <div className="h-3.5 bg-gray-100 rounded w-4/5" />
          <div className="h-3.5 bg-gray-100 rounded w-full" />
          <div className="h-3.5 bg-gray-100 rounded w-3/4" />
        </div>
      )}

      {!loading && error && (
        <p className="text-sm text-gray-400">{error}</p>
      )}

      {!loading && insight && !error && (
        <InsightText text={insight} />
      )}
    </div>
  );
}
