// Types partagés, alignés sur la sortie de aggregate.py.

export type NarrativeKey =
  | "URGENCE_MOBILISATION"
  | "SCIENCE_PEDAGOGIE"
  | "SOLUTIONS_TECHNO"
  | "SCEPTICISME_MINIMISATION"
  | "CRITIQUE_INACTION"
  | "OPPOSITION_ECOLOGIE"
  | "ANXIETE_EFFONDREMENT"
  | "HORS_SUJET";

export interface NarrativeStat {
  views: number;
  videos: number;
  views_pct: number;
  videos_pct: number;
  // Part venant des chaînes institutionnelles/annonceurs (soustraite quand
  // le toggle d'exclusion est actif).
  inst_views: number;
  inst_videos: number;
}

export interface ChannelStat {
  channel: string;
  channel_id: string;
  views: number;
  videos: number;
  institutional?: boolean;
}

export interface EvolutionRow {
  quarter: string;
  // Vrai sur le trimestre en cours (données partielles) — écarté des courbes.
  incomplete?: boolean;
  [key: string]: string | number | boolean | undefined;
}

export interface ToneRow {
  narratif: NarrativeKey;
  [tone: string]: string | number;
}

export interface Aggregates {
  meta: {
    generated_at: string;
    total_videos_collected: number;
    total_videos_classified: number;
    total_views: number;
    period_start: string | null;
    period_end: string | null;
    current_quarter?: string;
    narrative_keys: NarrativeKey[];
    tonalites: string[];
    institutional_channel_ids?: string[];
    institutional_views?: number;
    institutional_videos?: number;
    institutional_views_pct?: number;
  };
  narratives: Record<NarrativeKey, NarrativeStat>;
  evolution: EvolutionRow[];
  top_channels: Record<NarrativeKey, ChannelStat[]>;
  tonalite_by_narrative: ToneRow[];
  audience_evolution?: AudienceEvolutionRow[];
}

export interface AudienceEvolutionRow {
  quarter: string;
  analyzed_videos: number;
  analyzed_views: number;
  hostile_views: number;
  hostile_pct: number;
}

export type CommentClimate =
  | "adhesion_science"
  | "scepticisme_deni"
  | "hostilite_ecologie"
  | "complotisme"
  | "anxiete"
  | "moquerie"
  | "neutre"
  | "hors_sujet"
  | "mixte";

export interface CommentInfo {
  climat: CommentClimate | null;
  sceptique_pct: number | null;
  hostile_pct: number | null;
  virulence: number | null;
  n_comments: number;
  status: string | null;
}

export type CommentsMap = Record<string, CommentInfo>;

export interface VideoRow {
  video_id: string;
  title: string;
  channel_title: string;
  published_at: string;
  view_count: number;
  like_count: number | null;
  comment_count: number | null;
  duration_seconds: number;
  url: string;
  narratif_principal: NarrativeKey;
  narratif_secondaire: NarrativeKey | null;
  confiance: number;
  tonalite: string;
  presence_solutions: boolean;
  registre: string;
  justification: string;
  has_transcript: boolean;
  is_institutional?: boolean;
}
