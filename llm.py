"""
llm.py — abstraction multi-fournisseurs pour la classification.

On sélectionne le fournisseur via la variable d'env LLM_PROVIDER :
  - "anthropic" (défaut) : Claude (ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
  - "ollama"             : modèle local (OLLAMA_MODEL, OLLAMA_HOST) — GRATUIT
  - "openai"             : GPT (OPENAI_API_KEY, OPENAI_MODEL) — ex. gpt-4o-mini

Chaque fournisseur expose la même fonction complete(prompt, max_tokens) -> str.
Objectif : classer le corpus avec un modèle bon marché (ou local) plutôt qu'avec
Claude Sonnet, après validation contre la vérité-terrain (voir validate_llm.py).
"""

import os

import requests


def get_completer():
    """
    Retourne (complete, nom_fournisseur) selon LLM_PROVIDER.
    `complete(prompt, max_tokens)` renvoie le texte de la réponse (idéalement du JSON).
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic()
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

        def complete(prompt: str, max_tokens: int = 600) -> str:
            r = client.messages.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")

        return complete, f"anthropic:{model}"

    if provider == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

        def complete(prompt: str, max_tokens: int = 600) -> str:
            # format=json contraint Ollama à produire du JSON valide (idéal ici).
            r = requests.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0, "num_predict": max_tokens},
                },
                timeout=300,
            )
            r.raise_for_status()
            return r.json()["message"]["content"]

        return complete, f"ollama:{model}"

    if provider == "openai":
        key = os.environ["OPENAI_API_KEY"]
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

        def complete(prompt: str, max_tokens: int = 600) -> str:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=120,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

        return complete, f"openai:{model}"

    if provider == "gemini":
        key = os.environ["GEMINI_API_KEY"]
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        def complete(prompt: str, max_tokens: int = 600) -> str:
            r = requests.post(
                url, params={"key": key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "maxOutputTokens": max_tokens,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        return complete, f"gemini:{model}"

    raise ValueError(
        f"LLM_PROVIDER inconnu : {provider!r} (attendu : anthropic|ollama|openai|gemini)")
