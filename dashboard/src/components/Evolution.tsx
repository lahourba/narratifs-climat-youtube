import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Aggregates, NarrativeKey } from "../types";
import {
  NARRATIVE_COLORS,
  NARRATIVE_LABELS,
  NARRATIVE_ORDER,
  formatViews,
} from "../constants";

// Périodes proposées : la longue traîne 2013-2018, quasi vide, écrase le
// signal récent — d'où le défaut sur « depuis 2019 ».
const PERIODS = [
  { id: "all", label: "Tout", from: "" },
  { id: "2019", label: "Depuis 2019", from: "2019-Q1" },
  { id: "2022", label: "Depuis 2022", from: "2022-Q1" },
] as const;
type PeriodId = (typeof PERIODS)[number]["id"];

export default function Evolution({ data }: { data: Aggregates }) {
  const [normalized, setNormalized] = useState(false);
  const [period, setPeriod] = useState<PeriodId>("2019");

  const from = PERIODS.find((p) => p.id === period)?.from ?? "";
  // Trimestre en cours (incomplet) : écarté de la courbe, signalé en note.
  const excludedQuarter = data.evolution.find((r) => r.incomplete)?.quarter;
  // Le format YYYY-Qn se compare lexicographiquement.
  const rows = data.evolution
    .filter((r) => !r.incomplete && r.quarter >= from)
    .map((row) => ({
      ...row,
      __total: NARRATIVE_ORDER.reduce((s, k) => s + (Number(row[k]) || 0), 0),
    }));

  return (
    <section>
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-5">
        <div>
          <h2 className="text-lg font-semibold text-stone-900">
            Évolution des vues par narratif
          </h2>
          <p className="text-sm text-stone-500 mt-1 max-w-xl">
            Aires empilées des vues cumulées par trimestre de publication.
            {normalized
              ? " En mode 100 %, on lit la part relative de chaque narratif."
              : " En valeur absolue, on lit le volume d'audience."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 self-start">
          <div className="inline-flex rounded-md border border-stone-300 p-0.5 bg-stone-100 text-sm">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                onClick={() => setPeriod(p.id)}
                className={`px-3 py-1.5 rounded ${
                  period === p.id
                    ? "bg-white text-stone-900 shadow-sm font-medium"
                    : "text-stone-500"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setNormalized((v) => !v)}
            className="text-sm px-3 py-1.5 rounded-md border border-stone-300 bg-white hover:bg-stone-50 text-stone-700"
          >
            {normalized ? "Voir en valeur absolue" : "Voir en part (100 %)"}
          </button>
        </div>
      </div>

      <div className="bg-white border border-stone-200 rounded-lg p-4">
        <ResponsiveContainer width="100%" height={420}>
          <AreaChart
            data={rows}
            stackOffset={normalized ? "expand" : "none"}
            margin={{ top: 8, right: 12, bottom: 8, left: 4 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f0efed" vertical={false} />
            <XAxis
              dataKey="quarter"
              tick={{ fontSize: 12, fill: "#78716c" }}
              axisLine={{ stroke: "#e7e5e4" }}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) =>
                normalized ? `${Math.round(v * 100)}%` : formatViews(v)
              }
              domain={normalized ? [0, 1] : [0, "auto"]}
              ticks={normalized ? [0, 0.25, 0.5, 0.75, 1] : undefined}
              tick={{ fontSize: 12, fill: "#78716c" }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip content={<CustomTooltip normalized={normalized} />} />
            <Legend
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
              formatter={(value) => NARRATIVE_LABELS[value as NarrativeKey] ?? value}
            />
            {NARRATIVE_ORDER.map((key) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stackId="1"
                stroke={NARRATIVE_COLORS[key]}
                fill={NARRATIVE_COLORS[key]}
                fillOpacity={0.78}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-stone-400 mt-2">
        Les vues sont attribuées au trimestre de <em>publication</em> de la vidéo,
        pas au moment où elles ont été réalisées.
        {excludedQuarter &&
          ` Le trimestre en cours (${excludedQuarter}), incomplet, est exclu.`}
      </p>
    </section>
  );
}

interface TooltipProps {
  active?: boolean;
  label?: string;
  normalized: boolean;
  payload?: {
    dataKey: string;
    value: number;
    color: string;
    payload: { __total: number };
  }[];
}

function CustomTooltip({ active, label, payload, normalized }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  // En mode expand, Recharts remonte la valeur brute : on calcule la part
  // à partir du total du trimestre.
  const total = payload[0]?.payload?.__total ?? 0;
  // Tri décroissant pour lire les dominants en premier.
  const sorted = [...payload].sort((a, b) => b.value - a.value);
  return (
    <div className="bg-white border border-stone-200 rounded-md shadow-sm px-3 py-2 text-xs">
      <div className="font-semibold text-stone-800 mb-1">{label}</div>
      {sorted.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-stone-600">
          <span
            className="w-2.5 h-2.5 rounded-sm"
            style={{ backgroundColor: p.color }}
          />
          <span className="flex-1">
            {NARRATIVE_LABELS[p.dataKey as NarrativeKey]}
          </span>
          <span className="tabular-nums">
            {normalized
              ? `${total > 0 ? ((100 * p.value) / total).toFixed(1) : "0,0"}%`
              : formatViews(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}
