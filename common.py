"""
Helpers partagés : chargement/sauvegarde JSON atomique, logging simple,
parsing de durée ISO 8601. Importé par tous les scripts du pipeline.
"""

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

# Racine du projet et répertoire de stockage intermédiaire (JSON local, pas de DB en v1).
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def load_dotenv(path: str = None) -> None:
    """
    Charge un fichier .env (KEY=VALUE par ligne) dans os.environ, SANS écraser
    les variables déjà définies dans l'environnement. Évite une dépendance
    externe (python-dotenv) : parsing volontairement minimaliste.
    Lignes vides et commentaires (#) ignorés. Guillemets entourants retirés.
    """
    path = path or os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                # Retire un éventuel "export " en préfixe.
                if key.startswith("export "):
                    key = key[len("export "):].strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


# Chargement automatique du .env dès l'import de common (donc dans tous les scripts).
load_dotenv()


def ensure_data_dir() -> str:
    """Crée le dossier data/ si besoin et le retourne."""
    os.makedirs(DATA_DIR, exist_ok=True)
    return DATA_DIR


def data_path(filename: str) -> str:
    """Chemin absolu d'un fichier dans data/."""
    return os.path.join(DATA_DIR, filename)


def log(msg: str) -> None:
    """Log horodaté sur stderr (n'interfère pas avec une éventuelle sortie stdout)."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def load_json(path: str, default=None):
    """Charge un JSON, retourne `default` si le fichier est absent ou illisible."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log(f"Avertissement : impossible de lire {path} ({e}). Valeur par défaut utilisée.")
        return default


def save_json(path: str, data) -> None:
    """
    Écriture atomique : on écrit dans un fichier temporaire puis on le renomme,
    pour ne jamais laisser un JSON tronqué en cas d'interruption.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def now_iso() -> str:
    """Timestamp ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_ISO_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def iso_duration_to_seconds(duration: str) -> int:
    """Convertit une durée ISO 8601 YouTube (ex: 'PT12M3S') en secondes. 0 si invalide."""
    if not duration:
        return 0
    m = _ISO_DURATION_RE.fullmatch(duration)
    if not m:
        return 0
    parts = m.groupdict()
    total = 0
    total += int(parts["days"] or 0) * 86400
    total += int(parts["hours"] or 0) * 3600
    total += int(parts["minutes"] or 0) * 60
    total += int(parts["seconds"] or 0)
    return total


def truncate_words(text: str, max_words: int) -> str:
    """Tronque un texte aux `max_words` premiers mots."""
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])
