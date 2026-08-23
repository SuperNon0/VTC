"""Réglages applicatifs modifiables depuis l'interface (Paramètres).

Stockés en base (table `app_settings`, clé/valeur). Ils **priment** sur les
valeurs du `.env` : ainsi le super-admin peut configurer Cloudflare depuis l'UI
sans éditer de fichier. Le `.env` sert de valeur par défaut / d'amorce.
"""

from __future__ import annotations

from flask import current_app

from .db import get_db


def get_setting(key: str, default: str | None = None) -> str | None:
    row = get_db().execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row is not None else default


def set_setting(key: str, value: str) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()


def cf_config() -> dict:
    """Config Cloudflare effective : la base d'abord, sinon le .env."""
    team = get_setting("cf_team_domain")
    if team is None:
        team = current_app.config.get("CF_ACCESS_TEAM_DOMAIN", "")
    aud = get_setting("cf_aud")
    if aud is None:
        aud = current_app.config.get("CF_ACCESS_AUD", "")
    verify = get_setting("cf_verify_jwt")
    if verify is None:
        verify_bool = bool(current_app.config.get("CF_VERIFY_JWT", True))
    else:
        verify_bool = verify == "1"
    # Normalise l'équipe : on veut juste le nom (ex. « super-nono »), même si
    # l'utilisateur colle le domaine complet « super-nono.cloudflareaccess.com ».
    t = (team or "").strip().removeprefix("https://").removeprefix("http://").strip("/")
    if t.endswith(".cloudflareaccess.com"):
        t = t[: -len(".cloudflareaccess.com")]
    return {"team": t, "aud": (aud or "").strip(), "verify": verify_bool}
