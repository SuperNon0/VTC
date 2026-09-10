"""Accès aux données métier : courses, clients, grilles tarifaires, lieux.

Couche fine au-dessus de SQLite. Toute la logique d'affichage se base sur le
**conducteur assigné** (`conducteur_id`), jamais sur le créateur (cahier §5).
Le créateur dispose d'une vue séparée de ce qu'il a saisi (`courses_creees`).
"""

from __future__ import annotations

import json
import time
import unicodedata

from panel.db import get_db

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
# ─────────────────────────────────────────────────────────────────────────────
# Profils (nom d'affichage) — table métier `vtc_profils`, la base ne stockant que
# l'e-mail. Reliée à comptes.id par compte_id (convention du modèle en couches).
# ─────────────────────────────────────────────────────────────────────────────
def nom_profil(compte_id: int) -> str | None:
    row = get_db().execute(
        "SELECT nom FROM vtc_profils WHERE compte_id = ?", (compte_id,)
    ).fetchone()
    return (row["nom"] if row and row["nom"] else None)


def set_nom_profil(compte_id: int, nom: str | None) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO vtc_profils (compte_id, nom) VALUES (?, ?) "
        "ON CONFLICT(compte_id) DO UPDATE SET nom = excluded.nom",
        (compte_id, nom),
    )
    db.commit()


def conducteurs_actifs() -> list:
    """Comptes actifs pouvant se voir assigner une course (super_admin inclus)."""
    return get_db().execute(
        "SELECT c.id, c.email, p.nom AS nom, c.role FROM comptes c "
        "LEFT JOIN vtc_profils p ON p.compte_id = c.id "
        "WHERE c.etat = 'actif' "
        "ORDER BY (c.role = 'super_admin') DESC, COALESCE(p.nom, c.email)"
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
            tarif_id, distance_km, duree_min, statut, createur_id, conducteur_id,
            client_id, notes, cree, maj)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("client_nom"), data.get("client_tel"),
            data.get("depart"), data.get("arrivee"), data.get("quand"),
            data.get("prix"), data.get("prix_source"), data.get("tarif_id"),
            data.get("distance_km"), data.get("duree_min"),
            data.get("statut", "a_faire"),
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
        "SELECT c.*, COALESCE(p.nom, u.email) AS conducteur_email "
        "FROM courses c LEFT JOIN comptes u ON u.id = c.conducteur_id "
        "LEFT JOIN vtc_profils p ON p.compte_id = u.id "
        "WHERE c.createur_id = ? ORDER BY c.quand DESC",
        (createur_id,),
    ).fetchall()


def supprimer_course(course_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    db.commit()


def set_estimation(course_id: int, distance_km: float | None,
                   duree_min: int | None) -> None:
    """Enregistre l'estimation de trajet (distance + durée) d'une course."""
    db = get_db()
    db.execute(
        "UPDATE courses SET distance_km = ?, duree_min = ?, maj = ? WHERE id = ?",
        (distance_km, duree_min, int(time.time()), course_id),
    )
    db.commit()


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


def _sans_accents(s: str) -> str:
    """Minuscule + sans accents, pour une recherche tolérante (« paul » → « Paül »)."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def chercher_clients(q: str, limit: int = 8) -> list:
    """Autocomplétion par nom ou téléphone (cahier §6.4).

    Insensible à la casse ET aux accents : « paul » retrouve « Paul », « éric »
    retrouve « Eric ». La base de clients habitués est petite, on filtre donc en
    Python (comparaison normalisée) plutôt qu'avec un LIKE limité à l'ASCII.
    """
    qn = _sans_accents(q).strip()
    if not qn:
        return []
    out = []
    for row in get_db().execute("SELECT * FROM clients ORDER BY nom").fetchall():
        if qn in _sans_accents(row["nom"]) or qn in _sans_accents(row["telephone"] or ""):
            out.append(row)
            if len(out) >= limit:
                break
    return out


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
# Grilles tarifaires (cahier §6.3) — reliées à des lieux (départ → arrivée)
# ─────────────────────────────────────────────────────────────────────────────
def _nom_lieu(lieu_id: int | None) -> str | None:
    if not lieu_id:
        return None
    row = get_db().execute("SELECT nom FROM lieux WHERE id = ?", (lieu_id,)).fetchone()
    return row["nom"] if row else None


def _libelle_tarif(lieu_depart_id: int | None, lieu_arrivee_id: int | None) -> str:
    """Libellé auto d'un tarif à partir des lieux (évite la saisie en double)."""
    dep = _nom_lieu(lieu_depart_id)
    arr = _nom_lieu(lieu_arrivee_id)
    if dep and arr:
        return f"{dep} → {arr}"
    if arr:
        return f"→ {arr}"
    if dep:
        return f"{dep} → …"
    return "Tarif"


def liste_tarifs() -> list:
    """Tarifs avec les noms de lieux résolus (pour l'affichage et l'auto-match)."""
    return get_db().execute(
        "SELECT t.*, ld.nom AS depart_nom, la.nom AS arrivee_nom "
        "FROM tarifs t "
        "LEFT JOIN lieux ld ON ld.id = t.lieu_depart_id "
        "LEFT JOIN lieux la ON la.id = t.lieu_arrivee_id "
        "ORDER BY t.ordre, t.libelle"
    ).fetchall()


def creer_tarif(prix: float, lieu_depart_id: int | None,
                lieu_arrivee_id: int | None) -> int:
    db = get_db()
    ordre = (db.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM tarifs")
             .fetchone()[0])
    libelle = _libelle_tarif(lieu_depart_id, lieu_arrivee_id)
    cur = db.execute(
        "INSERT INTO tarifs (libelle, prix, lieu_depart_id, lieu_arrivee_id, ordre) "
        "VALUES (?, ?, ?, ?, ?)",
        (libelle, prix, lieu_depart_id, lieu_arrivee_id, ordre),
    )
    db.commit()
    return cur.lastrowid


def maj_tarif(tarif_id: int, prix: float, lieu_depart_id: int | None,
              lieu_arrivee_id: int | None) -> None:
    db = get_db()
    libelle = _libelle_tarif(lieu_depart_id, lieu_arrivee_id)
    db.execute(
        "UPDATE tarifs SET libelle = ?, prix = ?, lieu_depart_id = ?, "
        "lieu_arrivee_id = ? WHERE id = ?",
        (libelle, prix, lieu_depart_id, lieu_arrivee_id, tarif_id),
    )
    db.commit()


def supprimer_tarif(tarif_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM tarifs WHERE id = ?", (tarif_id,))
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Migration idempotente : colonnes ajoutées après coup sur une base existante.
# Appelée au démarrage par app/__init__.py::register (le schéma.sql ne sait pas
# faire « ALTER … ADD COLUMN IF NOT EXISTS »).
# ─────────────────────────────────────────────────────────────────────────────
def ensure_schema() -> None:
    db = get_db()
    cols = {r[1] for r in db.execute("PRAGMA table_info(lieux)").fetchall()}
    if cols and "ville_id" not in cols:   # table présente mais colonne manquante
        db.execute("ALTER TABLE lieux ADD COLUMN ville_id INTEGER")
        db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Villes desservies (liste gérable, rattachées aux lieux)
# ─────────────────────────────────────────────────────────────────────────────
def liste_villes() -> list:
    return get_db().execute(
        "SELECT * FROM villes ORDER BY ordre, nom"
    ).fetchall()


def creer_ville(nom: str) -> int:
    db = get_db()
    ordre = (db.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM villes")
             .fetchone()[0])
    cur = db.execute("INSERT INTO villes (nom, ordre) VALUES (?, ?)", (nom, ordre))
    db.commit()
    return cur.lastrowid


def supprimer_ville(ville_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM villes WHERE id = ?", (ville_id,))
    db.commit()


def ajouter_villes(noms) -> int:
    """Ajoute plusieurs villes d'un coup (coller-liste), en ignorant les doublons
    (insensible à la casse et aux accents). Renvoie le nombre réellement ajouté."""
    db = get_db()
    existing = {_sans_accents(r["nom"])
                for r in db.execute("SELECT nom FROM villes").fetchall()}
    ordre = db.execute("SELECT COALESCE(MAX(ordre), 0) FROM villes").fetchone()[0]
    n = 0
    for nom in noms:
        nom = (nom or "").strip()
        if not nom:
            continue
        key = _sans_accents(nom)
        if key in existing:
            continue
        existing.add(key)
        ordre += 1
        db.execute("INSERT INTO villes (nom, ordre) VALUES (?, ?)", (nom, ordre))
        n += 1
    db.commit()
    return n


# ─────────────────────────────────────────────────────────────────────────────
# Lieux fréquents (cahier §6.2) — rattachés à une ville
# ─────────────────────────────────────────────────────────────────────────────
def liste_lieux() -> list:
    """Lieux avec le nom de leur ville résolu (pour l'affichage et le filtrage)."""
    return get_db().execute(
        "SELECT l.*, v.nom AS ville_nom FROM lieux l "
        "LEFT JOIN villes v ON v.id = l.ville_id "
        "ORDER BY COALESCE(v.ordre, 999999), v.nom, l.ordre, l.nom"
    ).fetchall()


def creer_lieu(nom: str, adresse: str | None, ville_id: int | None = None) -> int:
    db = get_db()
    ordre = (db.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM lieux")
             .fetchone()[0])
    cur = db.execute(
        "INSERT INTO lieux (nom, adresse, ville_id, ordre) VALUES (?, ?, ?, ?)",
        (nom, adresse, ville_id, ordre),
    )
    db.commit()
    return cur.lastrowid


def supprimer_lieu(lieu_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM lieux WHERE id = ?", (lieu_id,))
    db.commit()
