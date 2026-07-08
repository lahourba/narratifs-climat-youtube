import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  AudienceEvolutionRow,
  CommentsMap,
  NarrativeKey,
  VideoRow,
} from "../types";
import {
  COMMENT_CLIMATE_COLORS,
  COMMENT_CLIMATE_LABELS,
  HOSTILE_CLIMATES,
  NARRATIVE_COLORS,
  NARRATIVE_LABELS,
  NARRATIVE_ORDER,
  formatInt,
  formatViews,
} from "../constants";

const CLIMATE_ORDER = [
  "adhesion_science",
  "neutre",
  "mixte",
  "moquerie",
  "anxiete",
  "scepticisme_deni",
  "hostilite_ecologie",
  "complotisme",
  "hors_sujet",
];

// Narratifs qui DÉFENDENT la science ou l'action dans leur propre discours.
// CRITIQUE_INACTION et ANXIETE_EFFONDREMENT sont volontairement exclus : sur
// une enquête à charge (greentech en faillite, violences en manif…), des
// commentaires hostiles vont souvent DANS LE SENS de la vidéo — ce n'est pas
// un écart vidéo ↔ audience, c'est une convergence.
const SUPPORTIVE = new Set<NarrativeKey>([
  "SCIENCE_PEDAGOGIE",
  "URGENCE_MOBILISATION",
  "SOLUTIONS_TECHNO",
]);

export default function Audience({
  videos,
  comments,
  hasComments,
  evolution = [],
}: {
  videos: VideoRow[];
  comments: CommentsMap;
  hasComments: boolean;
  evolution?: AudienceEvolutionRow[];
}) {
  const rows = useMemo(
    () =>
      videos
        .map((v) => ({ v, c: comments[v.video_id] }))
        .filter((r) => r.c && r.c.climat),
    [videos, comments]
  );

  if (!hasComments || rows.length === 0) {
    return (
      <div className="text-center py-20 text-stone-500">
        <p className="text-lg font-medium">Climat de l'audience — pas encore généré</p>
        <p className="mt-2 text-sm">
          Lance <code className="bg-stone-100 px-1 rounded">python comments.py --by-views --limit 500</code>{" "}
          pour analyser les sections de commentaires.
        </p>
      </div>
    );
  }

  const totalViews = rows.reduce((s, r) => s + r.v.view_count, 0);
  const hostileViews = rows
    .filter((r) => HOSTILE_CLIMATES.has(r.c!.climat!))
    .reduce((s, r) => s + r.v.view_count, 0);

  // Écart : vues de contenu « pro-science/action » baignant dans des commentaires hostiles.
  const supportiveRows = rows.filter((r) => SUPPORTIVE.has(r.v.narratif_principal));
  const supportiveViews = supportiveRows.reduce((s, r) => s + r.v.view_count, 0);
  const supportiveHostileViews = supportiveRows
    .filter((r) => HOSTILE_CLIMATES.has(r.c!.climat!))
    .reduce((s, r) => s + r.v.view_count, 0);

  // Matrice narratif × climat (nombre de vidéos).
  const matrix: Record<string, Record<string, number>> = {};
  NARRATIVE_ORDER.forEach((n) => {
    matrix[n] = {};
    CLIMATE_ORDER.forEach((c) => (matrix[n][c] = 0));
  });
  rows.forEach((r) => {
    const n = r.v.narratif_principal;
    if (matrix[n]) matrix[n][r.c!.climat!] = (matrix[n][r.c!.climat!] || 0) + 1;
  });
  const maxCell = Math.max(
    1,
    ...NARRATIVE_ORDER.flatMap((n) => CLIMATE_ORDER.map((c) => matrix[n][c]))
  );

  // Top divergences : contenu pro-science/action + commentaires hostiles, par vues.
  const divergences = supportiveRows
    .filter((r) => HOSTILE_CLIMATES.has(r.c!.climat!))
    .sort((a, b) => b.v.view_count - a.v.view_count)
    .slice(0, 12);

  return (
    <section>
      <div className="mb-5">
        <h2 className="text-lg font-semibold text-stone-900">
          Le climat de l'audience
        </h2>
        <p className="text-sm text-stone-500 mt-1 max-w-2xl">
          On analyse ici la <strong>section commentaires</strong> — la réaction du
          public, distincte du discours de la vidéo. {formatInt(rows.length)} vidéos
          analysées.
        </p>
      </div>

      {/* Indicateurs clés */}
      <div className="grid sm:grid-cols-3 gap-4 mb-8">
        <Stat
          value={`${Math.round((100 * hostileViews) / totalViews)}%`}
          label="des vues commentées sont dans une section hostile (sceptique, anti-écologie ou complotiste)"
        />
        <Stat
          value={`${Math.round((100 * supportiveHostileViews) / supportiveViews)}%`}
          label="des vues de contenu qui défend la science ou l'action (pédagogie, urgence, solutions) baignent pourtant dans des commentaires hostiles"
          accent
        />
        <Stat
          value={formatViews(supportiveHostileViews)}
          label="vues concernées par cet écart vidéo ↔ audience"
        />
      </div>

      {/* Évolution temporelle de la part hostile */}
      {evolution.length > 1 && (
        <div className="mb-8">
          <h3 className="text-base font-semibold text-stone-900 mb-1">
            La part d'audience hostile monte-t-elle ?
          </h3>
          <p className="text-sm text-stone-500 mb-3">
            Part des vues (par trimestre de publication) dont la section commentaires
            est hostile. <span className="text-stone-400">Signal volatil — le nombre de
            vidéos analysées par trimestre est encore faible. Les trimestres sous le
            seuil d'échantillon (moins de 5 vidéos et moins d'1 M de vues analysées)
            sont masqués.</span>
          </p>
          <div className="bg-white border border-stone-200 rounded-lg p-4">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={evolution} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0efed" vertical={false} />
                <XAxis
                  dataKey="quarter"
                  tick={{ fontSize: 12, fill: "#78716c" }}
                  axisLine={{ stroke: "#e7e5e4" }}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={(v) => `${v}%`}
                  domain={[0, "dataMax"]}
                  tick={{ fontSize: 12, fill: "#78716c" }}
                  axisLine={false}
                  tickLine={false}
                  width={40}
                />
                <Tooltip
                  formatter={(v: number, _name, item) => {
                    const r = item?.payload as AudienceEvolutionRow | undefined;
                    const detail = r
                      ? ` (${r.analyzed_videos} vidéos, ${formatViews(r.analyzed_views)} vues analysées)`
                      : "";
                    return [`${v}% hostile${detail}`, ""];
                  }}
                  labelStyle={{ fontWeight: 600 }}
                />
                <Area
                  type="monotone"
                  dataKey="hostile_pct"
                  stroke="#c1454f"
                  fill="#c1454f"
                  fillOpacity={0.18}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Matrice narratif × climat des commentaires */}
      <h3 className="text-base font-semibold text-stone-900 mb-3">
        Narratif de la vidéo × climat des commentaires
      </h3>
      <div className="overflow-x-auto border border-stone-200 rounded-lg bg-white">
        <table className="text-xs">
          <thead>
            <tr className="text-stone-500">
              <th className="text-left p-2 sticky left-0 bg-white">Narratif \ Commentaires</th>
              {CLIMATE_ORDER.map((c) => (
                <th key={c} className="p-2 align-bottom">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-sm mr-1"
                    style={{ backgroundColor: COMMENT_CLIMATE_COLORS[c] }}
                  />
                  <span className="whitespace-nowrap">{COMMENT_CLIMATE_LABELS[c]}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {NARRATIVE_ORDER.map((n) => (
              <tr key={n} className="border-t border-stone-100">
                <td className="p-2 whitespace-nowrap sticky left-0 bg-white">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-sm mr-1.5"
                    style={{ backgroundColor: NARRATIVE_COLORS[n] }}
                  />
                  {NARRATIVE_LABELS[n]}
                </td>
                {CLIMATE_ORDER.map((c) => {
                  const val = matrix[n][c];
                  const intensity = val / maxCell;
                  const hostile = HOSTILE_CLIMATES.has(c);
                  return (
                    <td
                      key={c}
                      className="p-2 text-center tabular-nums"
                      style={{
                        backgroundColor:
                          val === 0
                            ? "transparent"
                            : hostile
                            ? `rgba(193,69,79,${0.12 + 0.55 * intensity})`
                            : `rgba(74,124,89,${0.1 + 0.5 * intensity})`,
                        color: intensity > 0.6 ? "#fff" : "#44403c",
                      }}
                    >
                      {val || ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-stone-400 mt-2">
        Nombre de vidéos. Colonnes hostiles teintées en rouge, favorables en vert.
      </p>

      {/* Top divergences */}
      <h3 className="text-base font-semibold text-stone-900 mt-8 mb-3">
        Vidéos qui défendent la science ou l'action, aux commentaires les plus hostiles
      </h3>
      <p className="text-sm text-stone-500 -mt-2 mb-3 max-w-2xl">
        Pédagogie, urgence ou solutions dans la vidéo — scepticisme, hostilité ou
        complotisme en dessous. Les narratifs critiques (critique de l'inaction,
        effondrement) sont exclus&nbsp;: sur une enquête à charge, des commentaires
        hostiles vont souvent dans le sens de la vidéo, pas contre elle.
      </p>
      <div className="space-y-2">
        {divergences.map((r) => (
          <a
            key={r.v.video_id}
            href={r.v.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 border border-stone-200 rounded-lg bg-white hover:bg-stone-50"
          >
            <div className="flex-1 min-w-0">
              <div className="font-medium text-stone-900 truncate">{r.v.title}</div>
              <div className="text-xs text-stone-500 mt-0.5 flex flex-wrap gap-x-2 items-center">
                <Badge color={NARRATIVE_COLORS[r.v.narratif_principal]}>
                  {NARRATIVE_LABELS[r.v.narratif_principal]}
                </Badge>
                <span>→</span>
                <Badge color={COMMENT_CLIMATE_COLORS[r.c!.climat!]}>
                  {COMMENT_CLIMATE_LABELS[r.c!.climat!]}
                </Badge>
                <span className="text-stone-400">
                  {formatViews(r.v.view_count)} vues · {r.c!.sceptique_pct ?? "?"}% sceptique
                </span>
              </div>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

function Stat({
  value,
  label,
  accent,
}: {
  value: string;
  label: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        accent ? "border-red-200 bg-red-50" : "border-stone-200 bg-white"
      }`}
    >
      <div
        className={`text-2xl font-bold tabular-nums ${
          accent ? "text-red-700" : "text-stone-900"
        }`}
      >
        {value}
      </div>
      <div className="text-xs text-stone-600 mt-1 leading-snug">{label}</div>
    </div>
  );
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium"
      style={{ backgroundColor: `${color}22`, color }}
    >
      {children}
    </span>
  );
}
