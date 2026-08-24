"""Accès SQLite : schéma, connexion par requête, amorce du super-admin.

Schéma conforme à docs/authentification-v2.md §7 (table `comptes`) + un journal
d'audit (§9.2), enrichi du modèle métier taxi/VTC (cahier des charges §5) :
courses, clients habitués, grilles tarifaires, lieux fréquents et abonnements
Web Push.

Décision de cloisonnement (auth-v2 §7) : les courses forment une table
**partagée** avec propriété par ligne. Chaque course distingue explicitement le
**créateur** (qui l'a saisie) du **conducteur assigné** (à qui elle est
confiée) ; toute la logique d'affichage/notif/stats se base sur le conducteur
assigné, jamais sur le créateur (cahier §5).
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
    nom           TEXT,                              -- nom d'affichage (facultatif, ex. « Noé »)
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

-- Réglages configurables depuis l'UI (Cloudflare, fournisseur IA, VAPID…) : clé/valeur.
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ─────────────────────────── Modèle métier taxi/VTC ───────────────────────────

-- Clients habitués (cahier §6.4).
CREATE TABLE IF NOT EXISTS clients (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nom       TEXT NOT NULL,
    telephone TEXT,
    adresses  TEXT,             -- JSON : liste d'adresses fréquentes
    notes     TEXT,
    cree      INTEGER
);

-- Lieux fréquents présélectionnables dans le formulaire (cahier §6.2).
CREATE TABLE IF NOT EXISTS lieux (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nom     TEXT NOT NULL,      -- ex : « Gare du Grau-du-Roi »
    adresse TEXT,               -- adresse complète (optionnelle)
    ordre   INTEGER NOT NULL DEFAULT 0
);

-- Grilles tarifaires de base (cahier §6.3), gérées par le super-admin.
-- Un tarif relie un lieu de départ à un lieu d'arrivée (l'un des deux peut être
-- vide pour un forfait à sens unique) : cela permet la sélection AUTOMATIQUE du
-- tarif quand le départ et l'arrivée d'une course correspondent.
CREATE TABLE IF NOT EXISTS tarifs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    libelle         TEXT NOT NULL,   -- généré : « Départ → Arrivée »
    prix            REAL NOT NULL,
    lieu_depart_id  INTEGER,         -- lieu de départ (optionnel)
    lieu_arrivee_id INTEGER,         -- lieu d'arrivée (optionnel)
    ordre           INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (lieu_depart_id)  REFERENCES lieux(id) ON DELETE SET NULL,
    FOREIGN KEY (lieu_arrivee_id) REFERENCES lieux(id) ON DELETE SET NULL
);

-- Courses (cahier §5). Créateur ≠ conducteur assigné.
CREATE TABLE IF NOT EXISTS courses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_nom     TEXT,
    client_tel     TEXT,
    depart         TEXT,         -- adresse de prise en charge
    arrivee        TEXT,         -- adresse de dépose
    quand          INTEGER,      -- timestamp (date + heure de la course)
    prix           REAL,
    prix_source    TEXT,         -- 'grille' | 'autre' | 'distance' (évolution §6.3)
    tarif_id       INTEGER,      -- grille choisie, le cas échéant
    distance_km    REAL,         -- distance estimée du trajet (km), via OSM
    duree_min      INTEGER,      -- durée estimée du trajet (minutes), via OSM
    statut         TEXT NOT NULL DEFAULT 'a_faire',  -- a_faire|en_cours|terminee|annulee
    createur_id    INTEGER NOT NULL,   -- compte qui a saisi la course
    conducteur_id  INTEGER NOT NULL,   -- compte assigné (base de l'affichage/notif/stats)
    client_id      INTEGER,            -- client habitué lié (optionnel)
    notes          TEXT,
    cree           INTEGER,
    maj            INTEGER,
    FOREIGN KEY (createur_id)   REFERENCES comptes(id),
    FOREIGN KEY (conducteur_id) REFERENCES comptes(id),
    FOREIGN KEY (tarif_id)      REFERENCES tarifs(id) ON DELETE SET NULL,
    FOREIGN KEY (client_id)     REFERENCES clients(id) ON DELETE SET NULL
);

-- Index pour requêtes par conducteur/période (lisibilité stats §6.7, différé).
CREATE INDEX IF NOT EXISTS idx_courses_conducteur ON courses(conducteur_id, quand);
CREATE INDEX IF NOT EXISTS idx_courses_createur   ON courses(createur_id, quand);

-- Abonnements Web Push (cahier §6.5 / §7). Un appareil = une souscription.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    compte_id INTEGER NOT NULL,
    endpoint  TEXT NOT NULL UNIQUE,
    p256dh    TEXT NOT NULL,
    auth      TEXT NOT NULL,
    ua        TEXT,
    cree      INTEGER,
    FOREIGN KEY (compte_id) REFERENCES comptes(id) ON DELETE CASCADE
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
    _migrate(db)
    _seed_superadmin(db)


def _migrate(db: sqlite3.Connection) -> None:
    """Ajoute les colonnes manquantes sur les bases déjà créées (idempotent)."""
    def cols(table: str) -> set:
        return {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}

    tarifs = cols("tarifs")
    if "lieu_depart_id" not in tarifs:
        db.execute("ALTER TABLE tarifs ADD COLUMN lieu_depart_id INTEGER")
    if "lieu_arrivee_id" not in tarifs:
        db.execute("ALTER TABLE tarifs ADD COLUMN lieu_arrivee_id INTEGER")

    courses = cols("courses")
    if "duree_min" not in courses:
        db.execute("ALTER TABLE courses ADD COLUMN duree_min INTEGER")

    comptes = cols("comptes")
    if "nom" not in comptes:
        db.execute("ALTER TABLE comptes ADD COLUMN nom TEXT")
    db.commit()


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
    # Insertion ATOMIQUE et conditionnelle : sous gunicorn (plusieurs workers),
    # deux processus peuvent amorcer en même temps. SQLite sérialise les
    # écritures, donc le `WHERE NOT EXISTS` garantit un seul super-admin même en
    # cas de course (sinon on obtenait deux super-admins au premier démarrage).
    db.execute(
        "INSERT INTO comptes (email, role, etat, mdp_hash, cree, valide) "
        "SELECT ?, 'super_admin', 'actif', ?, ?, ? "
        "WHERE NOT EXISTS (SELECT 1 FROM comptes WHERE role = 'super_admin')",
        (email, generate_password_hash(password) if password else None, now, now),
    )
    db.commit()
    current_app.logger.info("Super-admin amorcé (email=%s, login local=%s).",
                            email or "—", bool(password))
