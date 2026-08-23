"""Accès SQLite : schéma, connexion par requête, amorce du super-admin.

Schéma conforme à docs/authentification-v2.md §7 (table `comptes`) + un journal
d'audit (§9.2). Le cloisonnement du contenu métier (§7 « partagée vs cloisonnée »)
est laissé à chaque projet — il n'y a pas encore de contenu dans le site de base.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS comptes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE,                       -- e-mail Google (NULL possible pour un super-admin local seul)
    role          TEXT NOT NULL DEFAULT 'membre',    -- super_admin | membre
    etat          TEXT NOT NULL DEFAULT 'pending',   -- pending | actif | refused | bloque
    mdp_hash      TEXT,                              -- seulement pour un compte à login local
    cree          INTEGER,                           -- timestamp de la demande / création
    valide        INTEGER,                           -- timestamp d'acceptation
    bloque        INTEGER,                           -- timestamp de blocage
    derniere_cnx  INTEGER
);

CREATE TABLE IF NOT EXISTS audit (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            INTEGER NOT NULL,
    acteur        TEXT,        -- e-mail / id de celui qui agit
    action        TEXT NOT NULL,
    cible         TEXT,        -- e-mail / id concerné
    detail        TEXT
);

-- Contenu du hub (bibliothèque partagée) : une seule ligne JSON.
CREATE TABLE IF NOT EXISTS hub (
    id   INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);

-- Réglages configurables depuis l'UI (ex. Cloudflare) : clé/valeur.
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_db() -> sqlite3.Connection:
    """Connexion SQLite attachée à la requête Flask courante."""
    if "db" not in g:
        path = current_app.config["DATABASE_PATH"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def audit(action: str, acteur: str | None = None, cible: str | None = None,
          detail: str | None = None) -> None:
    """Journalise une action sensible (validation, blocage, impersonation…)."""
    db = get_db()
    db.execute(
        "INSERT INTO audit (ts, acteur, action, cible, detail) VALUES (?, ?, ?, ?, ?)",
        (int(time.time()), acteur, action, cible, detail),
    )
    db.commit()


def init_db() -> None:
    """Crée le schéma et amorce le super-admin si absent (idempotent)."""
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
    _seed_superadmin(db)


def _seed_superadmin(db: sqlite3.Connection) -> None:
    """Insère (une fois) le super-admin d'après la config, s'il n'existe pas."""
    cfg = current_app.config
    email = (cfg.get("SUPERADMIN_EMAIL") or "").strip().lower() or None
    password = cfg.get("SUPERADMIN_PASSWORD") or ""

    row = db.execute("SELECT id, email FROM comptes WHERE role = 'super_admin' LIMIT 1").fetchone()
    if row is not None:
        # Rattache l'e-mail Google au super-admin s'il n'en a pas encore
        # (permet de le définir après coup via SUPERADMIN_EMAIL + redémarrage).
        if email and not row["email"]:
            db.execute("UPDATE comptes SET email = ? WHERE id = ?", (email, row["id"]))
            db.commit()
            current_app.logger.info("E-mail du super-admin rattaché : %s", email)
        return  # déjà amorcé

    if not password and not email:
        current_app.logger.warning(
            "Aucun super-admin amorcé : renseigne SUPERADMIN_PASSWORD et/ou "
            "SUPERADMIN_EMAIL dans .env."
        )
        return

    now = int(time.time())
    db.execute(
        "INSERT INTO comptes (email, role, etat, mdp_hash, cree, valide) "
        "VALUES (?, 'super_admin', 'actif', ?, ?, ?)",
        (email, generate_password_hash(password) if password else None, now, now),
    )
    db.commit()
    current_app.logger.info("Super-admin amorcé (email=%s, login local=%s).",
                            email or "—", bool(password))
