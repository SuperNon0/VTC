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


def update_course(course_id: int, data: dict) -> None:
    """Met à jour une course existante (le statut et le créateur sont conservés)."""
    db = get_db()
    db.execute(
        """UPDATE courses SET
             client_nom = ?, client_tel = ?, depart = ?, arrivee = ?, quand = ?,
             prix = ?, prix_source = ?, tarif_id = ?, distance_km = ?, duree_min = ?,
             conducteur_id = ?, client_id = ?, notes = ?, maj = ?
           WHERE id = ?""",
        (
            data.get("client_nom"), data.get("client_tel"),
            data.get("depart"), data.get("arrivee"), data.get("quand"),
            data.get("prix"), data.get("prix_source"), data.get("tarif_id"),
            data.get("distance_km"), data.get("duree_min"),
            data["conducteur_id"], data.get("client_id"),
            data.get("notes"), int(time.time()), course_id,
        ),
    )
    db.commit()


def promouvoir_courses_dues() -> None:
    """Passe automatiquement en « en cours » les courses « à faire » dont l'heure
    est arrivée (quand <= maintenant). Appelé à l'affichage des listes : pas de
    tâche de fond nécessaire. Le passage en « terminée » reste manuel (§5)."""
    now = int(time.time())
    db = get_db()
    db.execute(
        "UPDATE courses SET statut = 'en_cours', maj = ? "
        "WHERE statut = 'a_faire' AND quand IS NOT NULL AND quand <= ?",
        (now, now),
    )
    db.commit()


def _clause_statuts(statuts):
    """(fragment SQL, params) pour filtrer par un ensemble de statuts, ou ('', [])."""
    statuts = [s for s in (statuts or []) if s in STATUTS]
    if not statuts:
        return "", []
    return " AND statut IN (%s)" % ",".join("?" * len(statuts)), statuts


def courses_assignees(conducteur_id: int, statuts=None, order: str = "ASC") -> list:
    """Courses assignées à un conducteur (calendrier personnel §6.6).

    `statuts` = ensemble de statuts à garder (None = tous). Les courses passées
    ne sont PLUS masquées : elles restent tant qu'elles ne sont pas « terminée ».
    """
    frag, params = _clause_statuts(statuts)
    sens = "DESC" if str(order).upper() == "DESC" else "ASC"
    return get_db().execute(
        "SELECT * FROM courses WHERE conducteur_id = ?" + frag
        + " ORDER BY quand " + sens,
        [conducteur_id, *params],
    ).fetchall()


def courses_creees(createur_id: int, statuts=None, conducteur_id: int | None = None,
                   tri: str = "quand", order: str = "DESC") -> list:
    """Courses saisies par un créateur (§5), avec filtres statut / conducteur et
    tri par date-heure de course (`quand`) ou par date d'ajout (`cree`)."""
    frag, params = _clause_statuts(statuts)
    args = [createur_id, *params]
    if conducteur_id:
        frag += " AND c.conducteur_id = ?"
        args.append(conducteur_id)
    col = "c.cree" if tri == "cree" else "c.quand"
    sens = "ASC" if str(order).upper() == "ASC" else "DESC"
    return get_db().execute(
        "SELECT c.*, COALESCE(p.nom, u.email) AS conducteur_email "
        "FROM courses c LEFT JOIN comptes u ON u.id = c.conducteur_id "
        "LEFT JOIN vtc_profils p ON p.compte_id = u.id "
        "WHERE c.createur_id = ?" + frag
        + f" ORDER BY {col} {sens}",
        args,
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


def client_par_tel(telephone: str | None, exclude_id: int | None = None):
    """Renvoie le client existant ayant ce numéro (comparé sur les seuls chiffres),
    ou None. Sert à repérer les doublons de téléphone."""
    d = "".join(ch for ch in (telephone or "") if ch.isdigit())
    if not d:
        return None
    for r in get_db().execute("SELECT * FROM clients").fetchall():
        if exclude_id and r["id"] == exclude_id:
            continue
        rd = "".join(ch for ch in (r["telephone"] or "") if ch.isdigit())
        if rd and rd == d:
            return r
    return None


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
    """Adresses habituelles d'un client, normalisées en dicts {label, adresse}.

    Rétro-compatible : les anciennes adresses (simples chaînes JSON) sont
    converties en {label:"", adresse:<chaîne>}. Les vides sont ignorées.
    """
    try:
        raw = json.loads(row["adresses"] or "[]")
    except (ValueError, TypeError):
        return []
    return _normaliser_adresses(raw)


def _normaliser_adresses(raw) -> list:
    out = []
    for it in (raw or []):
        if isinstance(it, dict):
            adresse = (it.get("adresse") or "").strip()
            label = (it.get("label") or "").strip()
            ville = (it.get("ville") or "").strip()
        else:
            adresse = str(it or "").strip()
            label = ""
            ville = ""
        if adresse:
            out.append({"label": label, "ville": ville, "adresse": adresse})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Grilles tarifaires (cahier §6.3) — reliées à des lieux (départ → arrivée)
# ─────────────────────────────────────────────────────────────────────────────
def _nom_lieu(lieu_id: int | None) -> str | None:
    if not lieu_id:
        return None
    row = get_db().execute("SELECT nom FROM lieux WHERE id = ?", (lieu_id,)).fetchone()
    return row["nom"] if row else None


def _nom_ville(ville_id: int | None) -> str | None:
    if not ville_id:
        return None
    row = get_db().execute("SELECT nom FROM villes WHERE id = ?", (ville_id,)).fetchone()
    return row["nom"] if row else None


def _nom_extremite(lieu_id: int | None, ville_id: int | None) -> str | None:
    """Nom d'une extrémité de tarif : un lieu fréquent OU une ville."""
    return _nom_lieu(lieu_id) or _nom_ville(ville_id)


def _libelle_tarif(dep_lieu, dep_ville, arr_lieu, arr_ville) -> str:
    """Libellé auto d'un tarif (« Grau-du-Roi → Aigues-Mortes »), lieu ou ville."""
    dep = _nom_extremite(dep_lieu, dep_ville)
    arr = _nom_extremite(arr_lieu, arr_ville)
    if dep and arr:
        return f"{dep} → {arr}"
    if arr:
        return f"→ {arr}"
    if dep:
        return f"{dep} → …"
    return "Tarif"


def liste_tarifs() -> list:
    """Tarifs avec les noms d'extrémités résolus (lieu OU ville) — affichage + auto-match."""
    return get_db().execute(
        "SELECT t.*, "
        "COALESCE(ld.nom, vd.nom) AS depart_nom, "
        "COALESCE(la.nom, va.nom) AS arrivee_nom "
        "FROM tarifs t "
        "LEFT JOIN lieux  ld ON ld.id = t.lieu_depart_id "
        "LEFT JOIN lieux  la ON la.id = t.lieu_arrivee_id "
        "LEFT JOIN villes vd ON vd.id = t.ville_depart_id "
        "LEFT JOIN villes va ON va.id = t.ville_arrivee_id "
        "ORDER BY t.ordre, t.libelle"
    ).fetchall()


def creer_tarif(prix: float, dep_lieu=None, dep_ville=None,
                arr_lieu=None, arr_ville=None, bidir: bool = False) -> int:
    db = get_db()
    ordre = (db.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM tarifs")
             .fetchone()[0])
    libelle = _libelle_tarif(dep_lieu, dep_ville, arr_lieu, arr_ville)
    cur = db.execute(
        "INSERT INTO tarifs (libelle, prix, lieu_depart_id, lieu_arrivee_id, "
        "ville_depart_id, ville_arrivee_id, bidirectionnel, ordre) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (libelle, prix, dep_lieu, arr_lieu, dep_ville, arr_ville,
         1 if bidir else 0, ordre),
    )
    db.commit()
    return cur.lastrowid


def maj_tarif(tarif_id: int, prix: float, dep_lieu=None, dep_ville=None,
              arr_lieu=None, arr_ville=None, bidir: bool = False) -> None:
    db = get_db()
    libelle = _libelle_tarif(dep_lieu, dep_ville, arr_lieu, arr_ville)
    db.execute(
        "UPDATE tarifs SET libelle = ?, prix = ?, lieu_depart_id = ?, "
        "lieu_arrivee_id = ?, ville_depart_id = ?, ville_arrivee_id = ?, "
        "bidirectionnel = ? WHERE id = ?",
        (libelle, prix, dep_lieu, arr_lieu, dep_ville, arr_ville,
         1 if bidir else 0, tarif_id),
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
    # Tarifs ville → ville : colonnes ajoutées après coup sur une base existante.
    tcols = {r[1] for r in db.execute("PRAGMA table_info(tarifs)").fetchall()}
    if tcols:
        for col in ("ville_depart_id", "ville_arrivee_id"):
            if col not in tcols:
                db.execute(f"ALTER TABLE tarifs ADD COLUMN {col} INTEGER")
        if "bidirectionnel" not in tcols:
            db.execute("ALTER TABLE tarifs ADD COLUMN bidirectionnel INTEGER NOT NULL DEFAULT 0")
        db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Villes desservies (liste gérable, rattachées aux lieux)
# ─────────────────────────────────────────────────────────────────────────────
def liste_villes() -> list:
    return get_db().execute(
        "SELECT * FROM villes ORDER BY ordre, nom"
    ).fetchall()


def liste_villes_alpha() -> list:
    """Villes triées par ordre alphabétique (insensible aux accents)."""
    villes = get_db().execute("SELECT * FROM villes").fetchall()
    return sorted(villes, key=lambda v: _sans_accents(v["nom"]))


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


def maj_lieu(lieu_id: int, nom: str, adresse: str | None,
             ville_id: int | None = None) -> None:
    db = get_db()
    db.execute(
        "UPDATE lieux SET nom = ?, adresse = ?, ville_id = ? WHERE id = ?",
        (nom, adresse, ville_id, lieu_id),
    )
    db.commit()


def supprimer_lieu(lieu_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM lieux WHERE id = ?", (lieu_id,))
    db.commit()
