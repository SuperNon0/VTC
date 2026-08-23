"""Accès aux données métier : courses, clients, grilles tarifaires, lieux.

Couche fine au-dessus de SQLite. Toute la logique d'affichage se base sur le
**conducteur assigné** (`conducteur_id`), jamais sur le créateur (cahier §5).
Le créateur dispose d'une vue séparée de ce qu'il a saisi (`courses_creees`).
"""

from __future__ import annotations

import json
import time

from .db import get_db

# États d'une course (cahier §5).
STATUTS = ("a_faire", "en_cours", "terminee", "annulee")
STATUT_LABELS = {
    "a_faire": "À faire",
    "en_cours": "En cours",
    "terminee": "Terminée",
    "annulee": "Annulée",
}


# ─────────────────────────────────────────────────────────────────────────────
# Conducteurs (comptes actifs) — pour la liste d'assignation (cahier §6.5)
# ─────────────────────────────────────────────────────────────────────────────
def conducteurs_actifs() -> list:
    """Comptes actifs pouvant se voir assigner une course (super_admin inclus)."""
    return get_db().execute(
        "SELECT id, email, role FROM comptes WHERE etat = 'actif' "
        "ORDER BY (role = 'super_admin') DESC, email"
    ).fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# Courses
# ─────────────────────────────────────────────────────────────────────────────
def creer_course(data: dict, createur_id: int) -> int:
    """Insère une course. `data` est déjà validé/nettoyé par la route."""
    now = int(time.time())
    db = get_db()
    cur = db.execute(
        """INSERT INTO courses
           (client_nom, client_tel, depart, arrivee, quand, prix, prix_source,
            tarif_id, distance_km, statut, createur_id, conducteur_id, client_id,
            notes, cree, maj)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("client_nom"), data.get("client_tel"),
            data.get("depart"), data.get("arrivee"), data.get("quand"),
            data.get("prix"), data.get("prix_source"), data.get("tarif_id"),
            data.get("distance_km"), data.get("statut", "a_faire"),
            createur_id, data["conducteur_id"], data.get("client_id"),
            data.get("notes"), now, now,
        ),
    )
    db.commit()
    return cur.lastrowid


def get_course(course_id: int):
    return get_db().execute(
        "SELECT * FROM courses WHERE id = ?", (course_id,)
    ).fetchone()


def courses_assignees(conducteur_id: int, a_venir: bool = False) -> list:
    """Courses assignées à un conducteur (base du calendrier personnel, §6.6)."""
    db = get_db()
    if a_venir:
        return db.execute(
            "SELECT * FROM courses WHERE conducteur_id = ? AND statut != 'annulee' "
            "AND quand >= ? ORDER BY quand ASC",
            (conducteur_id, int(time.time()) - 3600),
        ).fetchall()
    return db.execute(
        "SELECT * FROM courses WHERE conducteur_id = ? ORDER BY quand DESC",
        (conducteur_id,),
    ).fetchall()


def courses_creees(createur_id: int) -> list:
    """Toutes les courses saisies par un créateur, quel que soit l'assigné (§5)."""
    return get_db().execute(
        "SELECT c.*, u.email AS conducteur_email "
        "FROM courses c LEFT JOIN comptes u ON u.id = c.conducteur_id "
        "WHERE c.createur_id = ? ORDER BY c.quand DESC",
        (createur_id,),
    ).fetchall()


def set_statut(course_id: int, statut: str) -> bool:
    if statut not in STATUTS:
        return False
    db = get_db()
    db.execute(
        "UPDATE courses SET statut = ?, maj = ? WHERE id = ?",
        (statut, int(time.time()), course_id),
    )
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Clients habitués (cahier §6.4)
# ─────────────────────────────────────────────────────────────────────────────
def liste_clients() -> list:
    return get_db().execute("SELECT * FROM clients ORDER BY nom").fetchall()


def get_client(client_id: int):
    return get_db().execute(
        "SELECT * FROM clients WHERE id = ?", (client_id,)
    ).fetchone()


def chercher_clients(q: str, limit: int = 8) -> list:
    """Autocomplétion : recherche par nom ou téléphone (cahier §6.4)."""
    like = f"%{q}%"
    return get_db().execute(
        "SELECT * FROM clients WHERE nom LIKE ? OR telephone LIKE ? "
        "ORDER BY nom LIMIT ?",
        (like, like, limit),
    ).fetchall()


def creer_client(nom: str, telephone: str | None, adresses: list | None,
                 notes: str | None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO clients (nom, telephone, adresses, notes, cree) "
        "VALUES (?, ?, ?, ?, ?)",
        (nom, telephone, json.dumps(adresses or [], ensure_ascii=False),
         notes, int(time.time())),
    )
    db.commit()
    return cur.lastrowid


def maj_client(client_id: int, nom: str, telephone: str | None,
               adresses: list | None, notes: str | None) -> None:
    db = get_db()
    db.execute(
        "UPDATE clients SET nom = ?, telephone = ?, adresses = ?, notes = ? "
        "WHERE id = ?",
        (nom, telephone, json.dumps(adresses or [], ensure_ascii=False),
         notes, client_id),
    )
    db.commit()


def supprimer_client(client_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    db.commit()


def client_adresses(row) -> list:
    try:
        return json.loads(row["adresses"] or "[]")
    except (ValueError, TypeError):
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Grilles tarifaires (cahier §6.3)
# ─────────────────────────────────────────────────────────────────────────────
def liste_tarifs() -> list:
    return get_db().execute(
        "SELECT * FROM tarifs ORDER BY ordre, libelle"
    ).fetchall()


def creer_tarif(libelle: str, prix: float, concurrent: str | None) -> int:
    db = get_db()
    ordre = (db.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM tarifs")
             .fetchone()[0])
    cur = db.execute(
        "INSERT INTO tarifs (libelle, prix, concurrent, ordre) VALUES (?, ?, ?, ?)",
        (libelle, prix, concurrent, ordre),
    )
    db.commit()
    return cur.lastrowid


def maj_tarif(tarif_id: int, libelle: str, prix: float,
              concurrent: str | None) -> None:
    db = get_db()
    db.execute(
        "UPDATE tarifs SET libelle = ?, prix = ?, concurrent = ? WHERE id = ?",
        (libelle, prix, concurrent, tarif_id),
    )
    db.commit()


def supprimer_tarif(tarif_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM tarifs WHERE id = ?", (tarif_id,))
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Lieux fréquents (cahier §6.2)
# ─────────────────────────────────────────────────────────────────────────────
def liste_lieux() -> list:
    return get_db().execute(
        "SELECT * FROM lieux ORDER BY ordre, nom"
    ).fetchall()


def creer_lieu(nom: str, adresse: str | None) -> int:
    db = get_db()
    ordre = (db.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM lieux")
             .fetchone()[0])
    cur = db.execute(
        "INSERT INTO lieux (nom, adresse, ordre) VALUES (?, ?, ?)",
        (nom, adresse, ordre),
    )
    db.commit()
    return cur.lastrowid


def supprimer_lieu(lieu_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM lieux WHERE id = ?", (lieu_id,))
    db.commit()
