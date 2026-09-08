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
from datetime import datetime

import requests

from panel.settings import get_setting

# Modèles par défaut (gratuits au moment du développement — modifiables en
# Paramètres si les offres évoluent).
DEFAULTS = {
    "gemini": "gemini-3.6-flash",
    "mistral": "mistral-small-latest",
    "groq": "llama-3.3-70b-versatile",
}

PROVIDER_LABELS = {
    "gemini": "Google Gemini (AI Studio)",
    "mistral": "Mistral AI",
    "groq": "Groq",
}

_TIMEOUT = 20

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _build_prompt(message: str) -> str:
    """Construit le prompt en injectant la date courante (pour « demain », etc.)."""
    now = datetime.now()
    return (
        "Tu es un assistant pour une société de taxi. On te donne le message brut "
        "d'un client qui demande une course. Extrais uniquement les informations "
        "présentes, sans rien inventer.\n"
        f"Date et heure actuelles : {now:%Y-%m-%d %H:%M} "
        f"({_JOURS[now.weekday()]}). Utilise-les pour résoudre les dates relatives.\n"
        "Réponds STRICTEMENT en JSON avec ces clés (chaîne vide si absent) :\n"
        '{"nom": "...", "telephone": "...", "prise_en_charge": "...", '
        '"depose": "...", "date_heure": "..."}\n'
        "- nom : le nom du client.\n"
        "- telephone : son numéro de téléphone tel qu'écrit.\n"
        "- prise_en_charge : l'adresse ou le lieu de départ.\n"
        "- depose : l'adresse ou le lieu d'arrivée.\n"
        "- date_heure : la date et l'heure de prise en charge, au format "
        "AAAA-MM-JJTHH:MM sur 24 heures. Résous les expressions relatives par "
        "rapport à la date actuelle ci-dessus : « aujourd'hui », « demain », "
        "« après-demain », « dans 3 jours », « lundi prochain », « ce soir »… "
        "Interprète « midi » = 12:00, « midi et demi / midi trente » = 12:30, "
        "« minuit » = 00:00, « et quart » = :15, « moins le quart » = :45. Si une "
        "date est donnée sans heure, mets 00:00. Chaîne vide si aucune date n'est "
        "mentionnée.\n"
        "Ne renvoie que le JSON, sans texte autour.\n\nMessage du client :\n"
        + message
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
    """Extrait {nom, telephone, prise_en_charge, depose, date_heure} d'un message.

    `date_heure` est renvoyée au format « AAAA-MM-JJTHH:MM » (prête pour le champ
    datetime-local), les dates relatives (demain, après-demain, lundi prochain…)
    étant résolues d'après la date courante injectée dans le prompt. Lève
    `AIError` (message clair) si l'IA n'est pas configurée ou échoue.
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
        raw = PROVIDERS[provider](_build_prompt(message), cfg["model"], cfg["key"])
    except requests.RequestException as exc:
        raise AIError(f"Fournisseur IA injoignable : {exc}") from exc

    parsed = _parse_json(raw)
    return {
        "nom": (parsed.get("nom") or "").strip(),
        "telephone": (parsed.get("telephone") or "").strip(),
        "prise_en_charge": (parsed.get("prise_en_charge") or "").strip(),
        "depose": (parsed.get("depose") or "").strip(),
        "date_heure": _normalize_dt(parsed.get("date_heure")),
    }


def _normalize_dt(value) -> str:
    """Normalise la date renvoyée par l'IA en « AAAA-MM-JJTHH:MM » (sinon vide).

    Tolère l'espace au lieu du T et d'éventuelles secondes.
    """
    s = (str(value) if value is not None else "").strip().replace(" ", "T")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", s)
    if not m:
        return ""
    y, mo, d, h, mi = (int(x) for x in m.groups())
    # Validité basique (évite d'injecter une date absurde dans le champ).
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= h <= 23 and 0 <= mi <= 59):
        return ""
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}"


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
