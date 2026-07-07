import { useMemo, useState } from "react";
import type { CommentInfo, CommentsMap, NarrativeKey, VideoRow } from "../types";
import {
  COMMENT_CLIMATE_COLORS,
  COMMENT_CLIMATE_LABELS,
  NARRATIVE_COLORS,
  NARRATIVE_LABELS,
  NARRATIVE_ORDER,
  formatInt,
} from "../constants";

type SortKey = "view_count" | "published_at" | "confiance";

export default function Explorateur({
  videos,
  comments = {},
}: {
  videos: VideoRow[];
  comments?: CommentsMap;
}) {
  const [filter, setFilter] = useState<NarrativeKey | "all">("all");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("view_count");
  const [sortDesc, setSortDesc] = useState(true);

  const rows = useMemo(() => {
    let r = videos;
    if (filter !== "all") r = r.filter((v) => v.narratif_principal === filter);
    if (search.trim()) {
      const q = search.toLowerCase();
      r = r.filter(
        (v) =>
          v.title.toLowerCase().includes(q) ||
          v.channel_title.toLowerCase().includes(q)
      );
    }
    const sorted = [...r].sort((a, b) => {
      let av: number | string = a[sortKey] ?? 0;
      let bv: number | string = b[sortKey] ?? 0;
      if (sortKey === "published_at") {
        av = a.published_at;
        bv = b.published_at;
        return sortDesc ? bv.localeCompare(av) : av.localeCompare(bv);
      }
      return sortDesc ? (bv as number) - (av as number) : (av as number) - (bv as number);
    });
    return sorted;
  }, [videos, filter, search, sortKey, sortDesc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDesc((d) => !d);
    else {
      setSortKey(key);
      setSortDesc(true);
    }
  }

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-stone-900">
          Explorateur de vidéos
        </h2>
        <p className="text-sm text-stone-500 mt-1">
          {formatInt(rows.length)} vidéo{rows.length > 1 ? "s" : ""} ·
          filtrez par narratif, triez les colonnes, cliquez pour ouvrir sur YouTube.
        </p>
      </div>

      {/* Filtres */}
      <div className="flex flex-wrap gap-2 mb-3">
        <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
          Tous
        </FilterChip>
        {NARRATIVE_ORDER.map((key) => (
          <FilterChip
            key={key}
            active={filter === key}
            color={NARRATIVE_COLORS[key]}
            onClick={() => setFilter(key)}
          >
            {NARRATIVE_LABELS[key]}
          </FilterChip>
        ))}
      </div>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Rechercher un titre ou une chaîne…"
        className="w-full sm:w-80 mb-4 px-3 py-2 text-sm border border-stone-300 rounded-md focus:outline-none focus:ring-2 focus:ring-stone-300"
      />

      {/* Tableau */}
      <div className="overflow-x-auto border border-stone-200 rounded-lg bg-white">
        <table className="w-full text-sm">
          <thead className="bg-stone-50 text-stone-500 text-left">
            <tr>
              <th className="py-2.5 px-3 font-medium">Vidéo</th>
              <th className="py-2.5 px-3 font-medium hidden md:table-cell">Narratif</th>
              <SortableTh
                label="Vues"
                active={sortKey === "view_count"}
                desc={sortDesc}
                onClick={() => toggleSort("view_count")}
              />
              <SortableTh
                label="Confiance"
                active={sortKey === "confiance"}
                desc={sortDesc}
                onClick={() => toggleSort("confiance")}
                className="hidden sm:table-cell"
              />
              <SortableTh
                label="Date"
                active={sortKey === "published_at"}
                desc={sortDesc}
                onClick={() => toggleSort("published_at")}
                className="hidden lg:table-cell"
              />
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 500).map((v) => (
              <tr
                key={v.video_id}
                className="border-t border-stone-100 hover:bg-stone-50 align-top"
              >
                <td className="py-2.5 px-3 max-w-md">
                  <a
                    href={v.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-stone-900 hover:text-blue-700 hover:underline font-medium line-clamp-2"
                    title={v.title}
                  >
                    {v.title}
                  </a>
                  <div className="text-xs text-stone-500 mt-0.5 flex items-center gap-1.5 flex-wrap">
                    <span>{v.channel_title}</span>
                    <ClimateChip info={comments[v.video_id]} />
                  </div>
                  {/* Narratif visible sur mobile (colonne dédiée masquée) */}
                  <div className="md:hidden mt-1">
                    <NarrativeBadge nk={v.narratif_principal} />
                  </div>
                </td>
                <td className="py-2.5 px-3 hidden md:table-cell">
                  <NarrativeBadge nk={v.narratif_principal} />
                  {v.narratif_secondaire && (
                    <div className="text-xs text-stone-400 mt-1">
                      + {NARRATIVE_LABELS[v.narratif_secondaire]}
                    </div>
                  )}
                </td>
                <td className="py-2.5 px-3 tabular-nums text-stone-700 whitespace-nowrap">
                  {formatInt(v.view_count)}
                </td>
                <td className="py-2.5 px-3 hidden sm:table-cell">
                  <ConfidenceBar value={v.confiance} />
                </td>
                <td className="py-2.5 px-3 text-stone-500 hidden lg:table-cell whitespace-nowrap">
                  {v.published_at?.slice(0, 10)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 500 && (
        <p className="text-xs text-stone-400 mt-2">
          Affichage limité aux 500 premières vidéos (sur {formatInt(rows.length)}).
          Affinez le filtre ou la recherche.
        </p>
      )}
    </section>
  );
}

function FilterChip({
  active,
  color,
  onClick,
  children,
}: {
  active: boolean;
  color?: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border ${
        active
          ? "border-stone-900 bg-stone-900 text-white"
          : "border-stone-300 bg-white text-stone-600 hover:border-stone-400"
      }`}
    >
      {color && (
        <span
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: active ? "#fff" : color }}
        />
      )}
      {children}
    </button>
  );
}

function ClimateChip({ info }: { info?: CommentInfo }) {
  if (!info || !info.climat) return null;
  const color = COMMENT_CLIMATE_COLORS[info.climat] || "#9ca3af";
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
      style={{ backgroundColor: `${color}22`, color }}
      title={`Climat des commentaires — ${info.sceptique_pct ?? "?"}% sceptique, ${info.hostile_pct ?? "?"}% hostile à l'écologie`}
    >
      💬 {COMMENT_CLIMATE_LABELS[info.climat] || info.climat}
    </span>
  );
}

function NarrativeBadge({ nk }: { nk: NarrativeKey }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded"
      style={{
        backgroundColor: `${NARRATIVE_COLORS[nk]}1a`,
        color: NARRATIVE_COLORS[nk],
      }}
    >
      {NARRATIVE_LABELS[nk]}
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-stone-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-stone-500 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-stone-500 tabular-nums">{pct}%</span>
    </div>
  );
}

function SortableTh({
  label,
  active,
  desc,
  onClick,
  className = "",
}: {
  label: string;
  active: boolean;
  desc: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <th className={`py-2.5 px-3 font-medium ${className}`}>
      <button
        onClick={onClick}
        className={`inline-flex items-center gap-1 ${
          active ? "text-stone-900" : "hover:text-stone-700"
        }`}
      >
        {label}
        <span className="text-[10px]">
          {active ? (desc ? "▼" : "▲") : "↕"}
        </span>
      </button>
    </th>
  );
}
