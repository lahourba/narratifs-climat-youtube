import type { NarrativeKey } from "./types";

// Libellés courts et lisibles pour l'affichage (les clés restent techniques).
export const NARRATIVE_LABELS: Record<NarrativeKey, string> = {
  URGENCE_MOBILISATION: "Urgence & mobilisation",
  SCIENCE_PEDAGOGIE: "Science & pédagogie",
  SOLUTIONS_TECHNO: "Solutions & techno",
  SCEPTICISME_MINIMISATION: "Scepticisme & minimisation",
  CRITIQUE_INACTION: "Critique de l'inaction",
  OPPOSITION_ECOLOGIE: "Opposition à l'écologie",
  ANXIETE_EFFONDREMENT: "Anxiété & effondrement",
  HORS_SUJET: "Hors-sujet",
};

// Définitions (réutilisées dans la note de méthode / infobulles).
export const NARRATIVE_DEFINITIONS: Record<NarrativeKey, string> = {
  URGENCE_MOBILISATION:
    "Le climat est une crise grave nécessitant une action forte et rapide.",
  SCIENCE_PEDAGOGIE:
    "Explication factuelle des mécanismes, données, rapports GIEC, registre neutre.",
  SOLUTIONS_TECHNO:
    "Focus sur les solutions : renouvelables, sobriété, innovation, gestes.",
  SCEPTICISME_MINIMISATION:
    "Remise en cause de la gravité, du consensus, ou de l'origine humaine.",
  CRITIQUE_INACTION:
    "Réclame plus d'action : inaction des gouvernements, greenwashing, lobby fossile.",
  OPPOSITION_ECOLOGIE:
    "S'oppose aux politiques écologiques : écologie punitive, anti-ZFE, coût des renouvelables.",
  ANXIETE_EFFONDREMENT:
    "Registre anxiogène : collapsologie, fatalisme, éco-anxiété.",
  HORS_SUJET:
    "Le climat n'est qu'un prétexte/accroche : aucun narratif climatique substantiel.",
};

// Palette sobre mais distinguable, une couleur par narratif.
export const NARRATIVE_COLORS: Record<NarrativeKey, string> = {
  URGENCE_MOBILISATION: "#c1454f", // rouge sobre
  SCIENCE_PEDAGOGIE: "#2f7d8a", // sarcelle
  SOLUTIONS_TECHNO: "#4a7c59", // vert
  SCEPTICISME_MINIMISATION: "#c08a3e", // ambre
  CRITIQUE_INACTION: "#6b5b95", // violet
  OPPOSITION_ECOLOGIE: "#b06a3a", // terracotta
  ANXIETE_EFFONDREMENT: "#6b7280", // gris ardoise
  HORS_SUJET: "#cbd5e1", // gris clair
};

// Ordre canonique d'affichage.
// HORS_SUJET est volontairement absent : exclu du rapport côté agrégation
// (aggregate.py) et ne doit apparaître dans aucune vue.
export const NARRATIVE_ORDER: NarrativeKey[] = [
  "URGENCE_MOBILISATION",
  "SCIENCE_PEDAGOGIE",
  "SOLUTIONS_TECHNO",
  "SCEPTICISME_MINIMISATION",
  "CRITIQUE_INACTION",
  "OPPOSITION_ECOLOGIE",
  "ANXIETE_EFFONDREMENT",
];

// Couleurs des tonalités (graphe tonalité × narratif).
export const TONE_COLORS: Record<string, string> = {
  urgence: "#c1454f",
  anxiété: "#6b7280",
  neutre: "#9ca3af",
  optimisme: "#4a7c59",
  colère: "#b45309",
  moquerie: "#a16207",
};

// --- Climat de la section commentaires (dimension « audience ») ---
export const COMMENT_CLIMATE_LABELS: Record<string, string> = {
  adhesion_science: "Adhésion à la science",
  scepticisme_deni: "Scepticisme / déni",
  hostilite_ecologie: "Hostilité à l'écologie",
  complotisme: "Complotisme",
  anxiete: "Anxiété",
  moquerie: "Moquerie",
  neutre: "Neutre",
  hors_sujet: "Hors-sujet",
  mixte: "Mixte",
};

export const COMMENT_CLIMATE_COLORS: Record<string, string> = {
  adhesion_science: "#4a7c59",
  scepticisme_deni: "#c08a3e",
  hostilite_ecologie: "#c1454f",
  complotisme: "#7c3aed",
  anxiete: "#6b7280",
  moquerie: "#a16207",
  neutre: "#9ca3af",
  hors_sujet: "#cbd5e1",
  mixte: "#0e7490",
};

// Climats « problématiques » (hostiles à l'écologie / à la science).
export const HOSTILE_CLIMATES = new Set([
  "scepticisme_deni",
  "hostilite_ecologie",
  "complotisme",
]);

// Formatage des grands nombres (vues) en français abrégé.
export function formatViews(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(".", ",")} M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} k`;
  return `${n}`;
}

export function formatInt(n: number): string {
  return n.toLocaleString("fr-FR");
}
