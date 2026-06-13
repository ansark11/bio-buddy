"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { TimeSeriesPoint } from "@/lib/types";

interface Props {
  data: TimeSeriesPoint[];
  metricName: string;
  unit?: string;
  color?: string;
}

export default function MetricChart({ data, metricName, unit = "", color = "#60A5FA" }: Props) {
  const formatted = data.map((d) => ({
    date: d.date.slice(0, 10),
    value: d.value,
  }));

  if (!formatted.length) {
    return (
      <div className="flex items-center justify-center h-32 text-muted text-sm">
        No data available
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={formatted} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#8FA3BF" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#8FA3BF" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${v}${unit ? ` ${unit}` : ""}`}
          width={60}
        />
        <Tooltip
          formatter={(v) => [`${v ?? ""} ${unit}`, metricName]}
          labelStyle={{ fontSize: 12, color: "#8FA3BF" }}
          contentStyle={{
            fontSize: 12,
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8,
            background: "#112240",
            color: "#E8F0FE",
          }}
        />
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} dot={false} activeDot={{ r: 4, fill: color }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
