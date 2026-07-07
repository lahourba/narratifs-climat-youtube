import { useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Aggregates, NarrativeKey } from "../types";
import {
  NARRATIVE_COLORS,
  NARRATIVE_DEFINITIONS,
  NARRATIVE_LABELS,
  NARRATIVE_ORDER,
  formatInt,
  formatViews,
} from "../constants";

type Metric = "views" | "videos";

export default function Cartographie({ data }: { data: Aggregates }) {
  const [metric, setMetric] = useState<Metric>("views");
  const [excludeHS, setExcludeHS] = useState(true);
  const [excludeInst, setExcludeInst] = useState(false);

  // Liste des narratifs affichés (option : exclure le hors-sujet).
  const keys = NARRATIVE_ORDER.filter((k) => !(excludeHS && k === "HORS_SUJET"));
  // Métriques par narratif, avec option d'exclusion des chaînes
  // institutionnelles/annonceurs (vues largement issues de campagnes pub).
  const viewsOf = (k: NarrativeKey) =>
    data.narratives[k].views -
    (excludeInst ? data.narratives[k].inst_views ?? 0 : 0);
  const videosOf = (k: NarrativeKey) =>
    data.narratives[k].videos -
    (excludeInst ? data.narratives[k].inst_videos ?? 0 : 0);
  // Totaux pour renormaliser les pourcentages selon les exclusions actives.
  const totViews = keys.reduce((s, k) => s + viewsOf(k), 0) || 1;
  const totVideos = keys.reduce((s, k) => s + videosOf(k), 0) || 1;

  // Données triées par la métrique sélectionnée (décroissant).
  const rows = keys
    .map((key) => ({
      key,
      label: NARRATIVE_LABELS[key],
      color: NARRATIVE_COLORS[key],
      views: viewsOf(key),
      videos: videosOf(key),
      views_pct: Math.round((1000 * viewsOf(key)) / totViews) / 10,
      videos_pct: Math.round((1000 * videosOf(key)) / totVideos) / 10,
    }))
    .sort((a, b) =>
      metric === "views" ? b.views_pct - a.views_pct : b.videos_pct - a.videos_pct
    );
  const hasHorsSujet = (data.narratives.HORS_SUJET?.videos ?? 0) > 0;
  const instPct = data.meta.institutional_views_pct ?? 0;

  const primaryKey = metric === "views" ? "views_pct" : "videos_pct";
  const secondaryKey = metric === "views" ? "videos_pct" : "views_pct";

  return (
    <section>
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-5">
        <div>
          <h2 className="text-lg font-semibold text-stone-900">
            Répartition des narratifs
          </h2>
          <p className="text-sm text-stone-500 mt-1 max-w-xl">
            {metric === "views"
              ? "Part de chaque narratif dans les vues totales — ce à quoi le public est réellement exposé."
              : "Part de chaque narratif dans le nombre de vidéos produites."}
            {((excludeHS && hasHorsSujet) || excludeInst) && (
              <span className="text-stone-400">
                {" "}
                {[
                  excludeHS && hasHorsSujet ? "Hors-sujet exclu" : null,
                  excludeInst ? "chaînes institutionnelles exclues" : null,
                ]
                  .filter(Boolean)
                  .join(", ")}
                , pourcentages renormalisés.
              </span>
            )}
          </p>
        </div>
        <Toggle metric={metric} onChange={setMetric} />
      </div>

      <div className="flex flex-col gap-1.5 mb-4 -mt-1">
        {hasHorsSujet && (
          <label className="flex items-center gap-2 text-sm text-stone-600 cursor-pointer">
            <input
              type="checkbox"
              checked={excludeHS}
              onChange={(e) => setExcludeHS(e.target.checked)}
              className="rounded border-stone-300"
            />
            Exclure le « hors-sujet » ({data.narratives["HORS_SUJET"].views_pct}% des vues —
            climat utilisé comme simple accroche)
          </label>
        )}
        {instPct > 0 && (
          <label className="flex items-center gap-2 text-sm text-stone-600 cursor-pointer">
            <input
              type="checkbox"
              checked={excludeInst}
              onChange={(e) => setExcludeInst(e.target.checked)}
              className="rounded border-stone-300"
            />
            Exclure les chaînes institutionnelles / annonceurs ({instPct}% des vues —
            Enedis, ministères, AFD… : visibilité largement issue de campagnes pub)
          </label>
        )}
      </div>

      {/* Graphe en barres horizontales */}
      <div className="bg-white border border-stone-200 rounded-lg p-4">
        <ResponsiveContainer width="100%" height={Math.max(280, rows.length * 64)}>
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 8, right: 56, bottom: 8, left: 8 }}
            barCategoryGap="22%"
          >
            <XAxis
              type="number"
              domain={[0, "dataMax"]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fontSize: 12, fill: "#78716c" }}
              axisLine={{ stroke: "#e7e5e4" }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={150}
              tick={{ fontSize: 12, fill: "#44403c" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={{ fill: "rgba(0,0,0,0.03)" }}
              content={<CustomTooltip />}
            />
            {/* Barre secondaire (l'autre métrique) en gris, pour montrer l'écart */}
            <Bar
              dataKey={secondaryKey}
              fill="#d6d3d1"
              radius={[0, 3, 3, 0]}
              barSize={9}
              isAnimationActive={false}
            />
            {/* Barre principale colorée par narratif */}
            <Bar dataKey={primaryKey} radius={[0, 3, 3, 0]} barSize={18} isAnimationActive={false}>
              {rows.map((r) => (
                <Cell key={r.key} fill={r.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-stone-400 mt-2">
          Barre épaisse&nbsp;: {metric === "views" ? "% des vues" : "% des vidéos"} ·
          barre fine grise&nbsp;: {metric === "views" ? "% des vidéos" : "% des vues"}.
          L'écart révèle les narratifs qui « sur-performent » en audience.
        </p>
      </div>

      {/* Tableau récapitulatif */}
      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-stone-500 border-b border-stone-200">
              <th className="py-2 pr-3 font-medium">Narratif</th>
              <th className="py-2 px-3 font-medium text-right">% vues</th>
              <th className="py-2 px-3 font-medium text-right">% vidéos</th>
              <th className="py-2 px-3 font-medium text-right">Vues</th>
              <th className="py-2 pl-3 font-medium text-right">Vidéos</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-b border-stone-100">
                <td className="py-2 pr-3">
                  <span className="inline-flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-sm shrink-0"
                      style={{ backgroundColor: r.color }}
                    />
                    <span title={NARRATIVE_DEFINITIONS[r.key as NarrativeKey]}>
                      {r.label}
                    </span>
                  </span>
                </td>
                <td className="py-2 px-3 text-right tabular-nums font-medium">
                  {r.views_pct}%
                </td>
                <td className="py-2 px-3 text-right tabular-nums text-stone-500">
                  {r.videos_pct}%
                </td>
                <td className="py-2 px-3 text-right tabular-nums text-stone-500">
                  {formatInt(r.views)}
                </td>
                <td className="py-2 pl-3 text-right tabular-nums text-stone-500">
                  {r.videos}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <TopChannels data={data} excludeInst={excludeInst} />
    </section>
  );
}

function Toggle({
  metric,
  onChange,
}: {
  metric: Metric;
  onChange: (m: Metric) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-stone-300 p-0.5 bg-stone-100 text-sm self-start">
      <button
        onClick={() => onChange("views")}
        className={`px-3 py-1.5 rounded ${
          metric === "views"
            ? "bg-white text-stone-900 shadow-sm font-medium"
            : "text-stone-500"
        }`}
      >
        Pondéré par les vues
      </button>
      <button
        onClick={() => onChange("videos")}
        className={`px-3 py-1.5 rounded ${
          metric === "videos"
            ? "bg-white text-stone-900 shadow-sm font-medium"
            : "text-stone-500"
        }`}
      >
        Par nombre de vidéos
      </button>
    </div>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: { label: string; views: number; videos: number; views_pct: number; videos_pct: number } }[];
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const r = payload[0].payload;
  return (
    <div className="bg-white border border-stone-200 rounded-md shadow-sm px-3 py-2 text-xs">
      <div className="font-semibold text-stone-800 mb-1">{r.label}</div>
      <div className="text-stone-600">
        {r.views_pct}% des vues · {formatViews(r.views)} vues
      </div>
      <div className="text-stone-600">
        {r.videos_pct}% des vidéos · {r.videos} vidéos
      </div>
    </div>
  );
}

function TopChannels({
  data,
  excludeInst,
}: {
  data: Aggregates;
  excludeInst: boolean;
}) {
  return (
    <div className="mt-8">
      <h3 className="text-base font-semibold text-stone-900 mb-3">
        Principales chaînes par narratif
      </h3>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {NARRATIVE_ORDER.map((key) => {
          const channels = (data.top_channels[key] || []).filter(
            (c) => !(excludeInst && c.institutional)
          );
          if (channels.length === 0) return null;
          return (
            <div
              key={key}
              className="border border-stone-200 rounded-lg p-3 bg-white"
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="w-3 h-3 rounded-sm"
                  style={{ backgroundColor: NARRATIVE_COLORS[key] }}
                />
                <span className="text-sm font-medium text-stone-800">
                  {NARRATIVE_LABELS[key]}
                </span>
              </div>
              <ol className="space-y-1">
                {channels.slice(0, 5).map((c) => (
                  <li
                    key={c.channel}
                    className="flex justify-between gap-2 text-xs text-stone-600"
                  >
                    <span className="truncate">
                      {c.channel}
                      {c.institutional && (
                        <span
                          className="ml-1 px-1 rounded bg-amber-100 text-amber-800 text-[10px] align-middle"
                          title="Chaîne institutionnelle / annonceur — visibilité largement issue de campagnes pub"
                        >
                          pub
                        </span>
                      )}
                    </span>
                    <span className="tabular-nums text-stone-400 shrink-0">
                      {formatViews(c.views)}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          );
        })}
      </div>
    </div>
  );
}
