"""Configuration du site de base, lue depuis l'environnement (.env).

Aucune valeur secrète n'est codée en dur : tout vient de variables
d'environnement, avec des valeurs par défaut sûres pour le développement local.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()  # charge le fichier .env s'il existe
except Exception:  # python-dotenv absent : on lit l'environnement tel quel
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # --- Flask ---
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me-in-.env")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Passe SESSION_COOKIE_SECURE=true dès que tu es derrière HTTPS (Cloudflare).
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)

    # --- Identité / marque (template neutre : à personnaliser par projet) ---
    BRAND_PREFIX = os.getenv("BRAND_PREFIX", "site")       # partie dorée du logo
    BRAND_SUFFIX = os.getenv("BRAND_SUFFIX", "base")       # partie italique claire
    BRAND_BADGE = os.getenv("BRAND_BADGE", "template · fondation")

    # --- Base de données ---
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "site-base.db"))

    # --- Super-admin local (amorce au premier lancement) ---
    # Mot de passe du compte super-admin joignable en LAN (login par mot de passe).
    # Défini une seule fois à l'amorce ; ensuite géré en base.
    SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD", "")
    # E-mail Google du super-admin (celui autorisé dans Cloudflare Access).
    SUPERADMIN_EMAIL = os.getenv("SUPERADMIN_EMAIL", "")

    # --- Cloudflare Zero Trust (Access) ---
    # Équipe Cloudflare : https://<team>.cloudflareaccess.com
    CF_ACCESS_TEAM_DOMAIN = os.getenv("CF_ACCESS_TEAM_DOMAIN", "")  # ex: monequipe
    # AUD tag de l'application Access (obligatoire pour vérifier le JWT).
    CF_ACCESS_AUD = os.getenv("CF_ACCESS_AUD", "")
    # Vérifier le JWT Cf-Access-Jwt-Assertion (fortement recommandé, cf. spec §9).
    CF_VERIFY_JWT = _bool("CF_VERIFY_JWT", True)
    # En dev local sans Cloudflare, autorise l'entrée locale par mot de passe.
    ALLOW_LOCAL_LOGIN = _bool("ALLOW_LOCAL_LOGIN", True)

    # --- Notifications BotPanel ---
    # Adresse du BotPanel (https://github.com/SuperNon0/botpanel).
    BOTPANEL_URL = os.getenv("BOTPANEL_URL", "")
    BOTPANEL_TIMEOUT = float(os.getenv("BOTPANEL_TIMEOUT", "5"))
    # Slugs des notifications déclenchées par le cycle de vie des comptes.
    NOTIFY_SLUG_ACCESS_REQUEST = os.getenv("NOTIFY_SLUG_ACCESS_REQUEST", "acces_demande")
    NOTIFY_SLUG_ACCESS_VALIDATED = os.getenv("NOTIFY_SLUG_ACCESS_VALIDATED", "acces_valide")
    NOTIFY_SLUG_ACCESS_BLOCKED = os.getenv("NOTIFY_SLUG_ACCESS_BLOCKED", "acces_bloque")
