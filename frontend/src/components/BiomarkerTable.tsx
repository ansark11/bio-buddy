"use client";

import type { ExtractedBiomarker, HealthMetric } from "@/lib/types";

type BiomarkerRow = ExtractedBiomarker | HealthMetric;

function getFlag(row: BiomarkerRow): string | undefined {
  return row.flag ?? undefined;
}

function getFlagStyle(flag?: string): string {
  if (flag === "high") return "bg-red-900/30 text-bad";
  if (flag === "low")  return "bg-amber-900/30 text-warn";
  return "bg-green-900/30 text-ok";
}

interface Props {
  biomarkers: BiomarkerRow[];
}

export default function BiomarkerTable({ biomarkers }: Props) {
  if (!biomarkers.length) {
    return <p className="text-muted text-sm">No biomarkers to display.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-white/[0.08]">
            <th className="px-3 py-2 text-left text-[11px] font-semibold text-muted uppercase tracking-wide">Biomarker</th>
            <th className="px-3 py-2 text-left text-[11px] font-semibold text-muted uppercase tracking-wide">Value</th>
            <th className="px-3 py-2 text-left text-[11px] font-semibold text-muted uppercase tracking-wide">Unit</th>
            <th className="px-3 py-2 text-left text-[11px] font-semibold text-muted uppercase tracking-wide">Reference</th>
            <th className="px-3 py-2 text-left text-[11px] font-semibold text-muted uppercase tracking-wide">Status</th>
          </tr>
        </thead>
        <tbody>
          {biomarkers.map((b, i) => {
            const name   = "name" in b ? b.name : b.metric_name;
            const value  = "value" in b ? b.value : b.metric_value;
            const refLow = b.reference_range_low;
            const refHigh = b.reference_range_high;
            const flag   = getFlag(b);
            const refStr =
              refLow != null && refHigh != null ? `${refLow} – ${refHigh}`
              : refHigh != null ? `< ${refHigh}`
              : refLow  != null ? `>= ${refLow}`
              : "—";

            return (
              <tr key={i} className="border-t border-white/[0.06] hover:bg-cardhi transition-colors">
                <td className="px-3 py-2.5 font-medium text-ink">{name}</td>
                <td className="px-3 py-2.5 text-ink">{value}</td>
                <td className="px-3 py-2.5 text-muted">{b.unit}</td>
                <td className="px-3 py-2.5 text-muted text-xs">{refStr}</td>
                <td className="px-3 py-2.5">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getFlagStyle(flag)}`}>
                    {flag ?? "normal"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
