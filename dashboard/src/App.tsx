import { useState } from "react";
import aggregatesData from "./data/aggregates.json";
import videosData from "./data/videos.json";
import commentsData from "./data/comments.json";
import type { Aggregates, CommentsMap, VideoRow } from "./types";
import { formatInt } from "./constants";
import Cartographie from "./components/Cartographie";
import Evolution from "./components/Evolution";
import Explorateur from "./components/Explorateur";
import Audience from "./components/Audience";

const aggregates = aggregatesData as unknown as Aggregates;
const videos = videosData as unknown as VideoRow[];
const comments = commentsData as unknown as CommentsMap;
const hasComments = Object.keys(comments).length > 0;

type View = "cartographie" | "evolution" | "explorateur" | "audience";

const TABS: { id: View; label: string }[] = [
  { id: "cartographie", label: "Cartographie" },
  { id: "evolution", label: "Évolution" },
  { id: "audience", label: "Audience" },
  { id: "explorateur", label: "Explorateur" },
];

function formatPeriod(start: string | null, end: string | null): string {
  if (!start || !end) return "";
  return `${start.slice(0, 7)} → ${end.slice(0, 7)}`;
}

export default function App() {
  const [view, setView] = useState<View>("cartographie");
  const { meta } = aggregates;

  return (
    <div className="min-h-screen flex flex-col">
      {/* En-tête + note de méthode */}
      <header className="border-b border-stone-200 bg-white">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
            À quels récits sur le climat la France est-elle exposée sur YouTube ?
          </h1>
          <p className="mt-2 text-sm text-stone-600 leading-relaxed max-w-3xl">
            Cartographie des <strong>narratifs dominants</strong> dans les vidéos
            YouTube francophones sur le climat, pondérée par l'audience (vues).
            Chaque vidéo est classée par un modèle de langage selon sa narration
            principale parmi sept catégories.
          </p>
          <p className="mt-2 text-xs text-stone-500 leading-relaxed max-w-3xl">
            <strong>Périmètre&nbsp;:</strong> YouTube uniquement. Corpus issu de la
            recherche YouTube (requêtes de consensus <em>et</em> sceptiques pour
            limiter le biais). Échantillon non exhaustif&nbsp;: il reflète ce que la
            recherche YouTube remonte, pas l'intégralité de la plateforme.
          </p>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-stone-500">
            <span>{formatInt(meta.total_videos_classified)} vidéos classées</span>
            <span>{formatInt(meta.total_views)} vues cumulées</span>
            <span>{formatPeriod(meta.period_start, meta.period_end)}</span>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="border-b border-stone-200 bg-white sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setView(tab.id)}
              className={`px-3 sm:px-4 py-3 text-sm font-medium border-b-2 -mb-px ${
                view === tab.id
                  ? "border-stone-900 text-stone-900"
                  : "border-transparent text-stone-500 hover:text-stone-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      {/* Contenu */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-6">
        {meta.total_videos_classified === 0 ? (
          <EmptyState />
        ) : (
          <>
            {view === "cartographie" && <Cartographie data={aggregates} />}
            {view === "evolution" && <Evolution data={aggregates} />}
            {view === "audience" && (
              <Audience
                videos={videos}
                comments={comments}
                hasComments={hasComments}
                evolution={aggregates.audience_evolution ?? []}
              />
            )}
            {view === "explorateur" && (
              <Explorateur videos={videos} comments={comments} />
            )}
          </>
        )}
      </main>

      <footer className="border-t border-stone-200 bg-white">
        <div className="max-w-5xl mx-auto px-4 py-4 text-xs text-stone-400">
          Données générées le {meta.generated_at?.slice(0, 10)} · Classification
          assistée par IA, marge d'erreur assumée · Projet de cartographie des
          narratifs climat.
        </div>
      </footer>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-20 text-stone-500">
      <p className="text-lg font-medium">Aucune donnée à afficher</p>
      <p className="mt-2 text-sm">
        Lance le pipeline Python (collect → transcripts → classify → aggregate)
        pour générer <code className="bg-stone-100 px-1 rounded">aggregates.json</code>.
      </p>
    </div>
  );
}
