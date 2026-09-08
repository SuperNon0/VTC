"""Migration des données d'une base « VTC v1 » (template monolithique) vers le
modèle en couches (base verrouillée + surcouche `app/`).

À lancer **une fois**, sur la base de production existante, AVANT le premier
démarrage avec le nouveau socle :

    python app/migrate.py            # utilise DATABASE_PATH (.env)
    python app/migrate.py chemin.db  # ou un chemin explicite

Ce que fait la migration (idempotente — relançable sans risque) :

  1. `app_settings` : renomme les colonnes `key`/`value` (v1) en `cle`/`valeur`
     (attendues par la base v2). Sans ça, la base ne lirait plus ses réglages
     (Cloudflare, IA, VAPID…).
  2. Noms d'affichage : la base v2 ne stocke que l'e-mail des comptes. On recopie
     l'ancienne colonne `comptes.nom` (v1) dans la table métier `vtc_profils`.

Les tables métier (courses, clients, tarifs, lieux, push_subscriptions) ont un
schéma identique : elles sont conservées telles quelles (aucune action requise,
`app/schema.sql` les (re)crée en `IF NOT EXISTS`).
"""

from __future__ import annotations

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "base"))
sys.path.insert(0, ROOT)


def _db_path() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    from panel.config import Config
    return Config.DATABASE_PATH


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def migrer_app_settings(db: sqlite3.Connection) -> str:
    if not _table_exists(db, "app_settings"):
        return "app_settings absente — rien à faire."
    cols = _columns(db, "app_settings")
    if {"cle", "valeur"} <= cols:
        return "app_settings déjà au format v2 (cle/valeur)."
    if "key" in cols:
        db.execute("ALTER TABLE app_settings RENAME COLUMN key TO cle")
    if "value" in cols:
        db.execute("ALTER TABLE app_settings RENAME COLUMN value TO valeur")
    db.commit()
    return "app_settings migrée : key→cle, value→valeur ✓"


def migrer_noms(db: sqlite3.Connection) -> str:
    if not _table_exists(db, "comptes") or "nom" not in _columns(db, "comptes"):
        return "comptes.nom absente — aucun nom d'affichage à reprendre."
    db.execute(
        "CREATE TABLE IF NOT EXISTS vtc_profils ("
        " compte_id INTEGER PRIMARY KEY, nom TEXT,"
        " FOREIGN KEY (compte_id) REFERENCES comptes(id) ON DELETE CASCADE)"
    )
    rows = db.execute(
        "SELECT id, nom FROM comptes WHERE nom IS NOT NULL AND TRIM(nom) <> ''"
    ).fetchall()
    n = 0
    for cid, nom in rows:
        db.execute(
            "INSERT INTO vtc_profils (compte_id, nom) VALUES (?, ?) "
            "ON CONFLICT(compte_id) DO UPDATE SET nom = excluded.nom",
            (cid, nom),
        )
        n += 1
    db.commit()
    return f"Noms d'affichage repris dans vtc_profils : {n} compte(s) ✓"


def main() -> None:
    path = _db_path()
    if not os.path.isfile(path):
        print(f"Base introuvable : {path}")
        print("Rien à migrer (base neuve : elle sera créée au démarrage).")
        return
    print(f"Migration de : {path}")
    db = sqlite3.connect(path)
    try:
        print(" -", migrer_app_settings(db))
        print(" -", migrer_noms(db))
    finally:
        db.close()
    print("Migration terminée. Tu peux démarrer avec le nouveau socle.")


if __name__ == "__main__":
    main()
