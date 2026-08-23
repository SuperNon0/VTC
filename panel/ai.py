"""Extraction automatique des infos client depuis un message (cahier §6.1).

Contrainte impérative : **aucun abonnement payant**. On appelle une API IA à
usage gratuit (sans carte bancaire) directement en REST via `requests` — pas de
SDK lourd, ce qui rend le changement de fournisseur trivial.

Le fournisseur et sa clé sont **configurables depuis les Paramètres**
(super-admin) et stockés en base (`app_settings`), afin de pouvoir basculer
d'un fournisseur à l'autre sans repasser par le développement (cahier §6.1).

Fournisseurs pris en charge, par ordre de préférence du cahier :
  1. Google Gemini (AI Studio)  — free tier généreux, données UE non entraînées
  2. Mistral AI                 — alternative européenne, hébergement UE
  3. Groq                       — gratuit, très rapide, solution de secours

Pour en ajouter un : écrire une fonction `_call_<nom>` renvoyant le texte brut
du modèle, et l'enregistrer dans `PROVIDERS`.
"""

from __future__ import annotations

import json
import re

import requests

from .settings import get_setting

# Modèles par défaut (gratuits au moment du développement — modifiables en
# Paramètres si les offres évoluent).
DEFAULTS = {
    "gemini": "gemini-2.0-flash",
    "mistral": "mistral-small-latest",
    "groq": "llama-3.3-70b-versatile",
}

PROVIDER_LABELS = {
    "gemini": "Google Gemini (AI Studio)",
    "mistral": "Mistral AI",
    "groq": "Groq",
}

_TIMEOUT = 20

_PROMPT = (
    "Tu es un assistant pour une société de taxi. On te donne le message brut "
    "d'un client qui demande une course. Extrais uniquement les informations "
    "présentes, sans rien inventer. Réponds STRICTEMENT en JSON avec ces clés "
    "(chaîne vide si absent) :\n"
    '{"nom": "...", "telephone": "...", "prise_en_charge": "...", "depose": "..."}\n'
    "- nom : le nom du client.\n"
    "- telephone : son numéro de téléphone tel qu'écrit.\n"
    "- prise_en_charge : l'adresse ou le lieu de départ.\n"
    "- depose : l'adresse ou le lieu d'arrivée.\n"
    "Ne renvoie que le JSON, sans texte autour.\n\nMessage du client :\n"
)


class AIError(Exception):
    """Erreur d'extraction remontée proprement à l'utilisateur."""


def ai_config() -> dict:
    """Config IA effective (base uniquement — la clé n'est jamais dans le .env)."""
    provider = (get_setting("ai_provider") or "").strip().lower()
    model = (get_setting("ai_model") or "").strip()
    key = (get_setting("ai_api_key") or "").strip()
    return {
        "provider": provider,
        "model": model or DEFAULTS.get(provider, ""),
        "has_key": bool(key),
        "key": key,
    }


def is_configured() -> bool:
    cfg = ai_config()
    return bool(cfg["provider"] in PROVIDERS and cfg["has_key"])


# ─────────────────────────────────────────────────────────────────────────────
# Appels fournisseurs — chacun renvoie le texte brut produit par le modèle.
# ─────────────────────────────────────────────────────────────────────────────
def _call_gemini(prompt: str, model: str, key: str) -> str:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    r = requests.post(
        url,
        params={"key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "temperature": 0},
        },
        timeout=_TIMEOUT,
    )
    _raise_for_status(r, "Gemini")
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError(f"Réponse Gemini inattendue : {exc}") from exc


def _call_openai_like(base: str, prompt: str, model: str, key: str,
                      label: str) -> str:
    """Mistral et Groq partagent le format « chat completions » d'OpenAI."""
    r = requests.post(
        base,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=_TIMEOUT,
    )
    _raise_for_status(r, label)
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError(f"Réponse {label} inattendue : {exc}") from exc


def _call_mistral(prompt: str, model: str, key: str) -> str:
    return _call_openai_like("https://api.mistral.ai/v1/chat/completions",
                             prompt, model, key, "Mistral")


def _call_groq(prompt: str, model: str, key: str) -> str:
    return _call_openai_like("https://api.groq.com/openai/v1/chat/completions",
                             prompt, model, key, "Groq")


PROVIDERS = {
    "gemini": _call_gemini,
    "mistral": _call_mistral,
    "groq": _call_groq,
}


def _raise_for_status(r: requests.Response, label: str) -> None:
    if r.status_code >= 300:
        detail = r.text[:200]
        raise AIError(f"{label} a renvoyé HTTP {r.status_code} : {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────────────────────
def extract_course_info(message: str) -> dict:
    """Extrait {nom, telephone, prise_en_charge, depose} d'un message client.

    Lève `AIError` (message clair) si l'IA n'est pas configurée ou échoue.
    """
    message = (message or "").strip()
    if not message:
        raise AIError("Message vide.")

    cfg = ai_config()
    provider = cfg["provider"]
    if provider not in PROVIDERS:
        raise AIError(
            "Aucun fournisseur d'IA configuré. Le super-admin doit le régler "
            "dans Paramètres → Extraction IA."
        )
    if not cfg["has_key"]:
        raise AIError("Clé API manquante pour le fournisseur IA configuré.")

    try:
        raw = PROVIDERS[provider](_PROMPT + message, cfg["model"], cfg["key"])
    except requests.RequestException as exc:
        raise AIError(f"Fournisseur IA injoignable : {exc}") from exc

    parsed = _parse_json(raw)
    return {
        "nom": (parsed.get("nom") or "").strip(),
        "telephone": (parsed.get("telephone") or "").strip(),
        "prise_en_charge": (parsed.get("prise_en_charge") or "").strip(),
        "depose": (parsed.get("depose") or "").strip(),
    }


def _parse_json(raw: str) -> dict:
    """Tolère un éventuel bloc ```json … ``` ou du texte autour du JSON."""
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    raise AIError("L'IA n'a pas renvoyé de JSON exploitable.")
