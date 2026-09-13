"""Écrans métier taxi/VTC (surcouche `app/`) — branchés sur la base verrouillée.

Deux blueprints :
  - `main`   : calendrier du conducteur, création/détail de course, mes courses,
               statistiques, clients (autocomplétion), Web Push, export ICS, PWA.
  - `config` : réglages métier (IA, tarifs, lieux, calendrier, notifications,
               clients) inclus dans la page /reglages de la base.

Toute la logique d'affichage se base sur le **conducteur assigné** (cahier §5).
Le super_admin est traité exactement comme un conducteur pour son propre
calendrier et ses stats (cahier §3).

Réutilise la base par simple import (jamais de modification de `base/`) :
  - `login_required`, `super_admin_required`, `current_compte`… → `panel.auth`
  - `get_db`, `audit`                                          → `panel.db`
  - `get_setting`, `set_setting`                               → `panel.settings`
  - `{% extends "base.html" %}` (via app/templates/_layout.html) → thème + cadre
"""

from __future__ import annotations

from datetime import datetime

from flask import (Blueprint, Response, abort, flash, jsonify, redirect,
                   render_template, request, session, url_for)

from panel.auth import (current_compte, get_compte, is_super_admin,
                        login_required, super_admin_required)
from panel.db import audit, get_db
from panel.settings import set_setting

from . import courses as C
from . import maps
from . import webpush
from .ai import (DEFAULTS, PROVIDER_LABELS, PROVIDERS, AIError, ai_config,
                 extract_course_info)
from .ai import is_configured as ai_configured
from .helpers import _MOIS
from .helpers import (CAL_PLACEHOLDERS, DEFAULT_CAL_NOTES, DEFAULT_CAL_TITLE,
                      NOTIF_PLACEHOLDERS, DEFAULT_NOTIF_BODY,
                      DEFAULT_NOTIF_TITLE, cal_notes_template,
                      adresse_complete, cal_title_template, course_ics, fmt_dt,
                      fmt_jour, format_tel, google_calendar_url, label_compte,
                      notif_body_template, notif_corps, notif_title_template,
                      notif_titre, tel_digits)

# Blueprint « écrans » : sert aussi les assets métier (app.css, sw.js, icônes,
# manifest) sous /app/ — indépendant du /static de la base.
main_bp = Blueprint("main", __name__, static_folder="static",
                    static_url_path="/app")

# Blueprint « réglages métier » (inclus dans /reglages de la base).
config_bp = Blueprint("config", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Contexte partagé : les réglages métier exposés à tous les templates de l'app.
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.app_context_processor
def _inject_app_globals():
    """Expose des drapeaux métier à TOUS les templates (dont le partial
    app_reglages.html inclus par la page /reglages de la base)."""
    return {
        "maps_enabled": maps.is_enabled(),
        "is_super_admin": is_super_admin(),
        # Nom lisible d'un compte dans les templates (nom d'affichage → e-mail).
        "nom_compte": label_compte,
        # Téléphone : affichage toujours espacé + chiffres pour un lien tel:.
        "format_tel": format_tel,
        "tel_digits": tel_digits,
        # Adresse + ville (sans doublon) pour l'affichage/le lien cliquable.
        "adresse_complete": adresse_complete,
    }


def _course_view(row) -> dict:
    """Enrichit une course pour l'affichage (labels + date formatée)."""
    d = dict(row)
    d["quand_fmt"] = fmt_dt(row["quand"])
    d["statut_label"] = C.STATUT_LABELS.get(row["statut"], row["statut"])
    return d


def _grouper_par_jour(rows) -> list:
    """Regroupe des courses (déjà triées par date) par journée."""
    groupes: list[dict] = []
    for row in rows:
        ts = row["quand"] or 0
        jour = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "—"
        if not groupes or groupes[-1]["jour"] != jour:
            label = fmt_jour(ts)   # « lundi 21 septembre 2026 »
            groupes.append({"jour": jour, "label": label, "courses": []})
        groupes[-1]["courses"].append(_course_view(row))
    return groupes


# ─────────────────────────────────────────────────────────────────────────────
# Filtres de statut (accueil + page Courses)
# ─────────────────────────────────────────────────────────────────────────────
# (clé, libellé, statuts gardés | None = tous, ordre)
FILTRES_STATUT = [
    ("actives",  "À faire",    ["a_faire", "en_cours"], "ASC"),   # défaut
    ("en_cours", "En cours",   ["en_cours"],            "ASC"),
    ("terminee", "Terminées",  ["terminee"],            "DESC"),
    ("annulee",  "Annulées",   ["annulee"],             "DESC"),
    ("toutes",   "Toutes",     None,                    "DESC"),
]
_FILTRES_MAP = {k: (lbl, st, order) for k, lbl, st, order in FILTRES_STATUT}


def _resoudre_filtre(defaut: str = "actives"):
    """(clé, statuts, ordre) à partir du paramètre ?f=… (repli sur `defaut`)."""
    key = (request.args.get("f") or defaut)
    if key not in _FILTRES_MAP:
        key = defaut
    _lbl, statuts, order = _FILTRES_MAP[key]
    return key, statuts, order


# Filtres par jour (accueil)
JOUR_FILTRES = [
    ("tous",       "Tous les jours"),
    ("aujourdhui", "Aujourd'hui"),
    ("demain",     "Demain"),
    ("jour",       "Un jour…"),
    ("periode",    "Période…"),
]


def _jour_bornes(key: str, du_str: str, au_str: str):
    """(debut, fin) en timestamps selon le filtre jour, ou (None, None)."""
    from datetime import timedelta
    now = datetime.now()
    jour0 = datetime(now.year, now.month, now.day)

    def fin_de(d):
        return d + timedelta(days=1) - timedelta(seconds=1)

    if key == "aujourdhui":
        return int(jour0.timestamp()), int(fin_de(jour0).timestamp())
    if key == "demain":
        d = jour0 + timedelta(days=1)
        return int(d.timestamp()), int(fin_de(d).timestamp())
    if key == "jour":
        try:
            if du_str:
                d = datetime.strptime(du_str, "%Y-%m-%d")
                return int(d.timestamp()), int(fin_de(d).timestamp())
        except ValueError:
            pass
        return None, None
    if key == "periode":
        debut = fin = None
        try:
            if du_str:
                debut = int(datetime.strptime(du_str, "%Y-%m-%d").timestamp())
        except ValueError:
            pass
        try:
            if au_str:
                fin = int(fin_de(datetime.strptime(au_str, "%Y-%m-%d")).timestamp())
        except ValueError:
            pass
        return debut, fin
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Calendrier personnel (dashboard / accueil) — cahier §6.6
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.route("/")
@login_required
def dashboard():
    compte = current_compte()
    C.promouvoir_courses_dues()   # « à faire » dont l'heure est passée → « en cours »
    filtre, statuts, order = _resoudre_filtre("actives")
    jour = request.args.get("j") or "tous"
    if jour not in {k for k, _ in JOUR_FILTRES}:
        jour = "tous"
    du = (request.args.get("du") or "").strip()
    au = (request.args.get("au") or "").strip()
    debut, fin = _jour_bornes(jour, du, au)
    rows = C.courses_assignees(compte["id"], statuts=statuts, order=order,
                               debut=debut, fin=fin)
    # Vue : liste (défaut) | mois | semaine. Pour le calendrier, on passe toutes
    # les courses filtrées par statut (sans filtre de jour) en JSON.
    vue = request.args.get("vue") or "liste"
    if vue not in ("liste", "mois", "semaine"):
        vue = "liste"
    cal_json = []
    if vue != "liste":
        for r in C.courses_assignees(compte["id"], statuts=statuts, order="ASC"):
            # Date ET heure formatées CÔTÉ SERVEUR (comme la vue liste), pour
            # éviter tout décalage de fuseau horaire dans le calendrier JS.
            q = r["quand"] or 0
            d = datetime.fromtimestamp(q) if q else None
            cal_json.append({
                "id": r["id"], "ts": q,
                "d": d.strftime("%Y-%m-%d") if d else "",
                "t": (f"{d.hour:02d}h{d.minute:02d}") if d else "",
                "client": r["client_nom"] or "",
                "depart": r["depart"] or "", "arrivee": r["arrivee"] or "",
                "prix": r["prix"], "statut": r["statut"],
            })
    return render_template(
        "dashboard.html",
        compte=compte,
        is_super_admin=is_super_admin(),
        groupes=_grouper_par_jour(rows),
        total=len(rows),
        filtres=FILTRES_STATUT,
        filtre_actif=filtre,
        jour_filtres=JOUR_FILTRES,
        jour_actif=jour,
        du=du, au=au,
        vue=vue,
        cal_json=cal_json,
        push_available=webpush.is_available(),
        deja_abonne=webpush.compte_a_des_souscriptions(compte["id"]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Détail d'une course
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.route("/course/<int:course_id>")
@login_required
def course_detail(course_id: int):
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if compte["id"] not in (course["conducteur_id"], course["createur_id"]):
        abort(403)
    db = get_db()
    cond = db.execute("SELECT id, email, role FROM comptes WHERE id = ?",
                      (course["conducteur_id"],)).fetchone()
    crea = db.execute("SELECT id, email, role FROM comptes WHERE id = ?",
                      (course["createur_id"],)).fetchone()
    return render_template(
        "course_detail.html",
        compte=compte,
        is_super_admin=is_super_admin(),
        c=_course_view(course),
        statuts=[(code, C.STATUT_LABELS[code]) for code in C.STATUTS],
        habitue=bool(course["client_id"]),
        conducteur_email=(label_compte(cond) if cond else None),
        createur_email=(label_compte(crea) if crea else None),
        est_conducteur=(compte["id"] == course["conducteur_id"]),
        duree_fmt=maps.fmt_duree(course["duree_min"]),
        maps_enabled=maps.is_enabled(),
    )


@main_bp.post("/course/<int:course_id>/supprimer")
@login_required
def course_supprimer(course_id: int):
    """Supprime une course (créateur, conducteur assigné ou super-admin)."""
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if (compte["id"] not in (course["conducteur_id"], course["createur_id"])
            and not is_super_admin()):
        abort(403)
    C.supprimer_course(course_id)
    flash("Course supprimée.", "info")
    return redirect(url_for("main.dashboard"))


@main_bp.post("/course/<int:course_id>/estimer")
@login_required
def course_estimer(course_id: int):
    """(Re)calcule l'estimation de trajet d'une course via OpenStreetMap."""
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        return jsonify(ok=False, error="introuvable"), 404
    if compte["id"] not in (course["conducteur_id"], course["createur_id"]):
        return jsonify(ok=False, error="non autorisé"), 403
    if not (course["depart"] and course["arrivee"]):
        return jsonify(ok=False, error="départ et arrivée requis"), 400
    est, raison = maps.estimate_or_reason(course["depart"], course["arrivee"])
    if not est:
        return jsonify(ok=False, error=raison), 502
    C.set_estimation(course_id, est["distance_km"], est["duree_min"])
    fmt = maps.fmt_duree(est["duree_min"])
    if est.get("approx"):
        fmt += " (approx.)"
    return jsonify(ok=True, distance_km=est["distance_km"],
                   duree_min=est["duree_min"], duree_fmt=fmt, note=raison)


# ─────────────────────────────────────────────────────────────────────────────
# Création d'une course — cahier §6.1 / §6.2 / §6.3 / §6.5
# ─────────────────────────────────────────────────────────────────────────────
def _course_form_ctx(compte) -> dict:
    """Contexte commun au formulaire de course (création ET modification)."""
    lieux = C.liste_lieux()
    tarifs = C.liste_tarifs()
    villes = C.liste_villes()
    return dict(
        compte=compte,
        is_super_admin=is_super_admin(),
        conducteurs=C.conducteurs_actifs(),
        lieux=lieux,
        tarifs=tarifs,
        villes=villes,
        villes_json=[{"id": v["id"], "nom": v["nom"]} for v in villes],
        lieux_json=[{"id": l["id"], "nom": l["nom"], "adresse": l["adresse"] or "",
                     "ville_id": l["ville_id"], "ville_nom": l["ville_nom"] or ""}
                    for l in lieux],
        tarifs_json=[{"id": t["id"], "prix": t["prix"],
                      "dep_lieu": t["lieu_depart_id"], "dep_ville": t["ville_depart_id"],
                      "arr_lieu": t["lieu_arrivee_id"], "arr_ville": t["ville_arrivee_id"],
                      "bidir": bool(t["bidirectionnel"])}
                     for t in tarifs],
        ai_on=ai_configured(),
    )


@main_bp.route("/nouvelle")
@login_required
def nouvelle_course():
    return render_template("nouvelle_course.html", **_course_form_ctx(current_compte()))


@main_bp.route("/course/<int:course_id>/modifier")
@login_required
def course_modifier(course_id: int):
    """Formulaire pré-rempli pour modifier une course existante."""
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if (compte["id"] not in (course["conducteur_id"], course["createur_id"])
            and not is_super_admin()):
        abort(403)
    ctx = _course_form_ctx(compte)
    # Date/heure séparées à partir du timestamp.
    date_val = heure_val = ""
    if course["quand"]:
        d = datetime.fromtimestamp(course["quand"])
        date_val, heure_val = d.strftime("%Y-%m-%d"), d.strftime("%H:%M")
    # Prix : grille pré-sélectionnée, sinon prix libre.
    if course["tarif_id"] and course["prix_source"] == "grille":
        sel_tarif, prix_libre_val = str(course["tarif_id"]), ""
    elif course["prix"] is not None:
        sel_tarif, prix_libre_val = "autre", f"{course['prix']:.2f}"
    else:
        sel_tarif, prix_libre_val = "", ""
    ctx.update(
        edit=True, crs=course,
        form_action=url_for("main.course_modifier_save", course_id=course_id),
        cancel_url=url_for("main.course_detail", course_id=course_id),
        submit_label="Enregistrer",
        date_val=date_val, heure_val=heure_val,
        sel_tarif=sel_tarif, prix_libre_val=prix_libre_val,
        sel_conducteur=course["conducteur_id"],
    )
    return render_template("nouvelle_course.html", **ctx)


@main_bp.route("/course/<int:course_id>/dupliquer")
@login_required
def course_dupliquer(course_id: int):
    """Nouvelle course pré-remplie à partir d'une existante, SANS l'horaire."""
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if (compte["id"] not in (course["conducteur_id"], course["createur_id"])
            and not is_super_admin()):
        abort(403)
    ctx = _course_form_ctx(compte)
    if course["tarif_id"] and course["prix_source"] == "grille":
        sel_tarif, prix_libre_val = str(course["tarif_id"]), ""
    elif course["prix"] is not None:
        sel_tarif, prix_libre_val = "autre", f"{course['prix']:.2f}"
    else:
        sel_tarif, prix_libre_val = "", ""
    ctx.update(
        edit=False, crs=course, titre="Dupliquer la course",
        form_action=url_for("main.api_creer_course"),
        cancel_url=url_for("main.course_detail", course_id=course_id),
        submit_label="Créer la course",
        date_val="", heure_val="",         # on repart sans horaire
        sel_tarif=sel_tarif, prix_libre_val=prix_libre_val,
        sel_conducteur=course["conducteur_id"],
    )
    return render_template("nouvelle_course.html", **ctx)


@main_bp.post("/course/<int:course_id>/modifier")
@login_required
def course_modifier_save(course_id: int):
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if (compte["id"] not in (course["conducteur_id"], course["createur_id"])
            and not is_super_admin()):
        abort(403)
    data, erreur = _lire_course_form(request.form)
    if erreur:
        flash(erreur, "error")
        return redirect(url_for("main.course_modifier", course_id=course_id))
    C.update_course(course_id, data)
    flash("Course modifiée ✓", "success")
    return redirect(url_for("main.course_detail", course_id=course_id))


@main_bp.post("/api/extract")
@login_required
def api_extract():
    """Extraction IA des infos client depuis un message brut (cahier §6.1)."""
    data = request.get_json(silent=True) or {}
    try:
        infos = extract_course_info(data.get("message", ""))
    except AIError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return jsonify(ok=True, infos=infos)


def _lire_course_form(f):
    """Valide et normalise le formulaire de course (création ET modification).

    Renvoie (data, erreur). `data` est prêt pour creer_course/update_course
    (sans `statut`, géré par l'appelant). `erreur` est un message ou None.
    """
    try:
        conducteur_id = int(f.get("conducteur_id", ""))
    except (TypeError, ValueError):
        conducteur_id = 0
    if conducteur_id not in {c["id"] for c in C.conducteurs_actifs()}:
        return None, "Choisis un conducteur assigné valide."

    # Date et heure : deux champs séparés → timestamp. L'heure vide vaut 00:00.
    date_str = (f.get("date") or "").strip()
    heure_str = (f.get("heure") or "").strip() or "00:00"
    quand = (_parse_datetime_local(f"{date_str}T{heure_str}") if date_str
             else _parse_datetime_local(f.get("quand", "")))
    if quand is None:
        return None, "Renseigne au moins une date valide."

    prix, prix_source, tarif_id = _resoudre_prix(f)
    depart = (f.get("depart") or "").strip() or None
    arrivee = (f.get("arrivee") or "").strip() or None

    # Estimation du trajet (durée + distance) via OpenStreetMap — best-effort.
    distance_km = duree_min = None
    if depart and arrivee:
        est = maps.estimate(depart, arrivee)
        if est:
            distance_km, duree_min = est["distance_km"], est["duree_min"]

    return {
        "client_nom": (f.get("client_nom") or "").strip() or None,
        "client_tel": (f.get("client_tel") or "").strip() or None,
        "depart": depart,
        "arrivee": arrivee,
        "quand": quand,
        "prix": prix,
        "prix_source": prix_source,
        "tarif_id": tarif_id,
        "distance_km": distance_km,
        "duree_min": duree_min,
        "conducteur_id": conducteur_id,
        "client_id": _int_or_none(f.get("client_id")),
        "notes": (f.get("notes") or "").strip() or None,
    }, None


@main_bp.post("/api/courses")
@login_required
def api_creer_course():
    """Crée une course, l'assigne, et notifie le conducteur assigné (§6.5)."""
    compte = current_compte()
    data, erreur = _lire_course_form(request.form)
    if erreur:
        flash(erreur, "error")
        return redirect(url_for("main.nouvelle_course"))
    data["statut"] = "a_faire"
    course_id = C.creer_course(data, compte["id"])

    # Notification push au conducteur assigné (jamais au créateur) — §5/§6.5.
    webpush.notifier_conducteur(
        data["conducteur_id"], notif_titre(data), notif_corps(data),
        url=url_for("main.course_detail", course_id=course_id),
    )
    flash("Course créée et assignée ✓", "success")
    return redirect(url_for("main.dashboard"))


# ─────────────────────────────────────────────────────────────────────────────
# Menu « Plus » + courses créées + statistiques
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.route("/plus")
@login_required
def plus():
    """Menu « Plus » : accès secondaires (stats, réglages, déconnexion)."""
    return render_template(
        "plus.html", compte=current_compte(), is_super_admin=is_super_admin())


@main_bp.route("/mes-courses")
@login_required
def mes_courses():
    compte = current_compte()
    C.promouvoir_courses_dues()
    filtre, statuts, _order = _resoudre_filtre("toutes")
    cond = _int_or_none(request.args.get("cond"))
    tri = "cree" if (request.args.get("tri") == "cree") else "quand"
    rows = [_course_view(r) for r in C.courses_creees(
        compte["id"], statuts=statuts, conducteur_id=cond, tri=tri, order="DESC")]
    return render_template(
        "mes_courses.html", compte=compte,
        is_super_admin=is_super_admin(), courses=rows,
        filtres=FILTRES_STATUT, filtre_actif=filtre,
        conducteurs=C.conducteurs_actifs(), cond_actif=cond, tri_actif=tri,
    )


# Périodes proposées sur la page Statistiques.
PERIODES_STATS = [
    ("mois",         "Ce mois-ci"),       # défaut
    ("mois_dernier", "Mois dernier"),
    ("90j",          "90 derniers jours"),
    ("annee",        "Cette année"),
    ("perso",        "Personnalisé…"),
    ("tout",         "Tout l'historique"),
]
_PERIODES_MAP = {k for k, _ in PERIODES_STATS}

_JOURS_COURT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def _mois_precedent(y: int, m: int):
    return (y, m - 1) if m > 1 else (y - 1, 12)


def _periode_bornes(key: str, du_str: str, au_str: str):
    """(debut, fin, label) en timestamps pour la période choisie.

    `fin` est une borne haute EXCLUSIVE (ou None = jusqu'à maintenant/sans fin).
    """
    from datetime import timedelta
    now = datetime.now()
    jour0 = datetime(now.year, now.month, now.day)

    def ts(d):
        return int(d.timestamp())

    if key == "mois":
        debut = datetime(now.year, now.month, 1)
        return ts(debut), None, f"{_MOIS[now.month - 1].capitalize()} {now.year}"
    if key == "mois_dernier":
        fin = datetime(now.year, now.month, 1)
        y, m = _mois_precedent(now.year, now.month)
        debut = datetime(y, m, 1)
        return ts(debut), ts(fin), f"{_MOIS[m - 1].capitalize()} {y}"
    if key == "90j":
        debut = jour0 - timedelta(days=89)
        return ts(debut), None, "90 derniers jours"
    if key == "annee":
        debut = datetime(now.year, 1, 1)
        return ts(debut), None, f"Année {now.year}"
    if key == "perso":
        debut = fin = None
        label_du = label_au = None
        try:
            if du_str:
                d = datetime.strptime(du_str, "%Y-%m-%d")
                debut = ts(d)
                label_du = d.strftime("%d/%m/%Y")
        except ValueError:
            pass
        try:
            if au_str:
                d = datetime.strptime(au_str, "%Y-%m-%d")
                fin = ts(d + timedelta(days=1))   # inclus le jour « au »
                label_au = d.strftime("%d/%m/%Y")
        except ValueError:
            pass
        if label_du and label_au:
            label = f"Du {label_du} au {label_au}"
        elif label_du:
            label = f"Depuis le {label_du}"
        elif label_au:
            label = f"Jusqu'au {label_au}"
        else:
            label = "Période personnalisée"
        return debut, fin, label
    return None, None, "Tout l'historique"


def _mois_iter(dy, dm, fy, fm):
    """Itère (année, mois) du premier au dernier mois inclus."""
    y, m = dy, dm
    while (y, m) <= (fy, fm):
        yield y, m
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)


def _calc_stats(conducteur_id: int, debut, fin) -> dict:
    """Agrège les courses d'un conducteur sur une période : KPIs + séries de
    graphiques (CA dans le temps, jours de semaine, statuts, top clients)."""
    from datetime import timedelta
    db = get_db()
    sql = ("SELECT quand, prix, statut, distance_km, duree_min, "
           "client_nom, client_id FROM courses WHERE conducteur_id = ?")
    params = [conducteur_id]
    if debut is not None:
        sql += " AND quand >= ?"
        params.append(debut)
    if fin is not None:
        sql += " AND quand < ?"
        params.append(fin)
    rows = db.execute(sql, params).fetchall()

    kpi = {"ca_realise": 0.0, "ca_prevu": 0.0, "nb_total": 0,
           "nb_terminees": 0, "nb_annulees": 0, "nb_a_venir": 0,
           "distance_km": 0.0, "duree_min": 0, "prix_moyen": 0.0,
           "taux_annulation": 0.0, "clients_distincts": 0}
    par_statut = {s: 0 for s in C.STATUTS}
    par_semaine = [0] * 7
    clients = {}                 # nom → {"nb", "ca"}
    ca_par_jour = {}             # "YYYY-MM-DD" → CA réalisé
    ts_list = [r["quand"] for r in rows if r["quand"]]

    for r in rows:
        statut = r["statut"]
        prix = r["prix"] or 0.0
        kpi["nb_total"] += 1
        par_statut[statut] = par_statut.get(statut, 0) + 1
        if r["quand"]:
            d = datetime.fromtimestamp(r["quand"])
            if statut != "annulee":
                par_semaine[d.weekday()] += 1
        if statut == "terminee":
            kpi["nb_terminees"] += 1
            kpi["ca_realise"] += prix
            kpi["distance_km"] += (r["distance_km"] or 0.0)
            kpi["duree_min"] += (r["duree_min"] or 0)
            if r["quand"]:
                k = datetime.fromtimestamp(r["quand"]).strftime("%Y-%m-%d")
                ca_par_jour[k] = ca_par_jour.get(k, 0.0) + prix
        elif statut in ("a_faire", "en_cours"):
            kpi["nb_a_venir"] += 1
            kpi["ca_prevu"] += prix
        elif statut == "annulee":
            kpi["nb_annulees"] += 1
        if statut != "annulee":
            nom = (r["client_nom"] or "").strip() or "Sans nom"
            c = clients.setdefault(nom, {"nb": 0, "ca": 0.0})
            c["nb"] += 1
            if statut == "terminee":
                c["ca"] += prix

    if kpi["nb_terminees"]:
        kpi["prix_moyen"] = kpi["ca_realise"] / kpi["nb_terminees"]
    if kpi["nb_total"]:
        kpi["taux_annulation"] = 100.0 * kpi["nb_annulees"] / kpi["nb_total"]
    kpi["clients_distincts"] = len([n for n in clients if n != "Sans nom"]) \
        + (1 if "Sans nom" in clients else 0)

    # ── Série « CA réalisé dans le temps » (jour si ≤ 62 jours, sinon mois) ──
    eff_debut = debut if debut is not None else (min(ts_list) if ts_list else None)
    eff_fin = (fin - 1) if fin is not None else (max(ts_list) if ts_list else None)
    ca_series = {"gran": "jour", "points": [], "max": 0.0}
    if eff_debut is not None and eff_fin is not None and eff_fin >= eff_debut:
        d0 = datetime.fromtimestamp(eff_debut)
        d1 = datetime.fromtimestamp(eff_fin)
        span_jours = (datetime(d1.year, d1.month, d1.day)
                      - datetime(d0.year, d0.month, d0.day)).days
        if span_jours <= 62:
            jour = datetime(d0.year, d0.month, d0.day)
            borne = datetime(d1.year, d1.month, d1.day)
            while jour <= borne:
                k = jour.strftime("%Y-%m-%d")
                ca_series["points"].append(
                    {"label": jour.strftime("%d/%m"), "val": ca_par_jour.get(k, 0.0)})
                jour += timedelta(days=1)
        else:
            ca_series["gran"] = "mois"
            ca_par_mois = {}
            for k, v in ca_par_jour.items():
                ca_par_mois[k[:7]] = ca_par_mois.get(k[:7], 0.0) + v
            mois = list(_mois_iter(d0.year, d0.month, d1.year, d1.month))
            if len(mois) > 24:            # garde les 24 derniers mois (lisibilité)
                mois = mois[-24:]
            for (y, m) in mois:
                k = f"{y:04d}-{m:02d}"
                ca_series["points"].append(
                    {"label": f"{m:02d}/{str(y)[2:]}", "val": ca_par_mois.get(k, 0.0)})
        ca_series["max"] = max((p["val"] for p in ca_series["points"]), default=0.0)
    # N'affiche qu'une étiquette d'axe sur `step` (≈ 8 max) pour éviter qu'elles
    # se chevauchent quand il y a beaucoup de jours.
    import math
    n_pts = len(ca_series["points"])
    ca_series["step"] = max(1, math.ceil(n_pts / 8)) if n_pts else 1

    statut_ordre = [("terminee", "Terminées"), ("en_cours", "En cours"),
                    ("a_faire", "À faire"), ("annulee", "Annulées")]
    statuts = [{"key": k, "label": lbl, "val": par_statut.get(k, 0)}
               for k, lbl in statut_ordre if par_statut.get(k, 0)]

    top_clients = sorted(
        ({"nom": n, "nb": v["nb"], "ca": v["ca"]} for n, v in clients.items()),
        key=lambda c: (c["ca"], c["nb"]), reverse=True)[:6]

    return {
        "kpi": kpi,
        "ca_series": ca_series,
        "semaine": [{"label": _JOURS_COURT[i], "val": par_semaine[i]} for i in range(7)],
        "semaine_max": max(par_semaine) if any(par_semaine) else 0,
        "statuts": statuts,
        "statut_total": sum(s["val"] for s in statuts),
        "top_clients": top_clients,
        "top_ca_max": max((c["ca"] for c in top_clients), default=0.0),
        "vide": kpi["nb_total"] == 0,
    }


@main_bp.route("/mes-stats")
@login_required
def mes_stats():
    """Tableau de bord statistique du conducteur effectif (cahier §6.7)."""
    compte = current_compte()
    periode = request.args.get("p") or "mois"
    if periode not in _PERIODES_MAP:
        periode = "mois"
    du = (request.args.get("du") or "").strip()
    au = (request.args.get("au") or "").strip()
    debut, fin, periode_label = _periode_bornes(periode, du, au)
    stats = _calc_stats(compte["id"], debut, fin)
    return render_template(
        "mes_stats.html", compte=compte,
        is_super_admin=is_super_admin(), stats=stats,
        periodes=PERIODES_STATS, periode_actif=periode,
        periode_label=periode_label, du=du, au=au,
        fmt_duree=maps.fmt_duree,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Statut d'une course (le conducteur assigné avance son statut)
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.post("/api/courses/<int:course_id>/statut")
@login_required
def api_statut(course_id: int):
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        return jsonify(ok=False, error="introuvable"), 404
    if compte["id"] not in (course["conducteur_id"], course["createur_id"]):
        return jsonify(ok=False, error="non autorisé"), 403
    statut = (request.form.get("statut") or "").strip()
    if not C.set_statut(course_id, statut):
        return jsonify(ok=False, error="statut invalide"), 400
    return jsonify(ok=True, statut=statut, label=C.STATUT_LABELS.get(statut))


# ─────────────────────────────────────────────────────────────────────────────
# Clients — autocomplétion (cahier §6.4)
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.get("/api/clients/search")
@login_required
def api_clients_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify(clients=[])
    out = []
    for row in C.chercher_clients(q):
        out.append({
            "id": row["id"], "nom": row["nom"],
            "telephone": row["telephone"] or "",
            "notes": row["notes"] or "",
            "adresses": C.client_adresses(row),   # [{label, adresse}, …]
        })
    return jsonify(clients=out)


# ─────────────────────────────────────────────────────────────────────────────
# Conversion d'un lien Google Maps (même court) en lien Waze — la résolution
# (suivi de redirection, extraction des coords / du nom) vit dans maps.py.
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.get("/api/maps-waze")
@login_required
def api_maps_waze():
    """Résout un lien Google Maps → lien Waze (ll= si coords, sinon q= lieu)."""
    from urllib.parse import quote_plus
    info = maps.resolve_maps(request.args.get("u") or "")
    if info.get("coords"):
        lat, lon = info["coords"]
        return jsonify(waze=f"https://waze.com/ul?ll={lat},{lon}&navigate=yes")
    if info.get("q"):
        return jsonify(waze=f"https://waze.com/ul?q={quote_plus(info['q'])}&navigate=yes")
    return jsonify(waze=None)


# ─────────────────────────────────────────────────────────────────────────────
# Export calendrier natif (cahier §6.6)
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.get("/course/<int:course_id>/ics")
@login_required
def course_ics_download(course_id: int):
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if compte["id"] not in (course["conducteur_id"], course["createur_id"]):
        abort(403)
    ics = course_ics(course)
    return Response(
        ics, mimetype="text/calendar",
        headers={"Content-Disposition":
                 f'attachment; filename="course-{course_id}.ics"'},
    )


@main_bp.get("/course/<int:course_id>/google")
@login_required
def course_google(course_id: int):
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if compte["id"] not in (course["conducteur_id"], course["createur_id"]):
        abort(403)
    return redirect(google_calendar_url(course))


# ─────────────────────────────────────────────────────────────────────────────
# Web Push — abonnement des appareils (cahier §6.5 / §7)
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.get("/api/push/key")
@login_required
def api_push_key():
    return jsonify(key=webpush.public_key(), available=webpush.is_available())


@main_bp.post("/api/push/subscribe")
@login_required
def api_push_subscribe():
    compte = current_compte()
    sub = request.get_json(silent=True) or {}
    ok = webpush.enregistrer_souscription(
        compte["id"], sub, request.headers.get("User-Agent"))
    return (jsonify(ok=True) if ok
            else (jsonify(ok=False, error="souscription invalide"), 400))


@main_bp.post("/api/push/unsubscribe")
@login_required
def api_push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    if endpoint:
        webpush.supprimer_souscription(endpoint)
    return jsonify(ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Service worker (servi à la racine pour un scope « / »)
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.get("/sw.js")
def service_worker():
    """Sert le service worker à la racine (scope « / » requis pour la PWA)."""
    import os

    from flask import send_from_directory
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    resp = send_from_directory(static_dir, "sw.js",
                               mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privés (main)
# ─────────────────────────────────────────────────────────────────────────────
def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_datetime_local(value: str):
    """Convertit un champ date/heure en timestamp Unix."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return int(datetime.strptime(value, fmt).timestamp())
        except ValueError:
            continue
    return None


def _resoudre_prix(f):
    """Retourne (prix, source, tarif_id) selon la grille ou le prix libre (§6.3)."""
    choix = (f.get("tarif_choix") or "").strip()
    if choix and choix != "autre":
        tarif_id = _int_or_none(choix)
        for t in C.liste_tarifs():
            if t["id"] == tarif_id:
                return float(t["prix"]), "grille", tarif_id
    prix_libre = (f.get("prix_libre") or "").strip().replace(",", ".")
    try:
        return (float(prix_libre) if prix_libre else None), "autre", None
    except ValueError:
        return None, "autre", None


# ═════════════════════════════════════════════════════════════════════════════
# RÉGLAGES MÉTIER (blueprint `config`) — inclus dans /reglages de la base
# ═════════════════════════════════════════════════════════════════════════════
def _acteur() -> str:
    c = get_compte(session.get("impersonator_id") or session.get("compte_id"))
    return (c["email"] if c and c["email"] else "super_admin")


# ── Extraction IA (cahier §6.1) — super-admin uniquement ─────────────────────
@config_bp.route("/reglages/ia")
@super_admin_required
def ia():
    return render_template(
        "config_ia.html",
        providers=PROVIDER_LABELS,
        defaults=DEFAULTS,
        cfg=ai_config(),
        impersonating=bool(session.get("impersonator_id")),
    )


@config_bp.route("/reglages/ia", methods=["POST"])
@super_admin_required
def ia_save():
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier ces réglages.", "error")
        return redirect(url_for("config.ia"))
    provider = (request.form.get("provider") or "").strip().lower()
    model = (request.form.get("model") or "").strip()
    key = (request.form.get("api_key") or "").strip()

    if provider and provider not in PROVIDERS:
        flash("Fournisseur inconnu.", "error")
        return redirect(url_for("config.ia"))

    set_setting("ai_provider", provider)
    set_setting("ai_model", model)
    if key:
        set_setting("ai_api_key", key)
    elif request.form.get("clear_key"):
        set_setting("ai_api_key", "")

    audit("config_ia", _acteur(), detail=f"provider={provider} model={model}")
    flash("Réglages d'extraction IA enregistrés.", "success")
    return redirect(url_for("config.ia"))


# ── Modèle d'export calendrier (cahier §6.6) — super-admin uniquement ────────
@config_bp.route("/reglages/calendrier")
@super_admin_required
def calendrier():
    return render_template(
        "config_calendrier.html",
        titre=cal_title_template(),
        notes=cal_notes_template(),
        default_titre=DEFAULT_CAL_TITLE,
        default_notes=DEFAULT_CAL_NOTES,
        placeholders=CAL_PLACEHOLDERS,
        impersonating=bool(session.get("impersonator_id")),
    )


@config_bp.route("/reglages/calendrier", methods=["POST"])
@super_admin_required
def calendrier_save():
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier ces réglages.", "error")
        return redirect(url_for("config.calendrier"))
    if request.form.get("reset"):
        set_setting("cal_title_template", "")
        set_setting("cal_notes_template", "")
        flash("Modèle de calendrier réinitialisé aux valeurs par défaut.", "info")
        return redirect(url_for("config.calendrier"))
    set_setting("cal_title_template", (request.form.get("titre") or "").strip())
    set_setting("cal_notes_template", (request.form.get("notes") or "").rstrip())
    audit("config_calendrier", _acteur())
    flash("Modèle d'export calendrier enregistré ✓", "success")
    return redirect(url_for("config.calendrier"))


# ── Grilles tarifaires (cahier §6.3) — accessible à tout conducteur actif ────
@config_bp.route("/reglages/tarifs")
@login_required
def tarifs():
    return render_template("config_tarifs.html",
                           tarifs=C.liste_tarifs(), lieux=C.liste_lieux(),
                           villes=C.liste_villes())


def _parse_endpoint(val):
    """Décode une extrémité de tarif : 'l:<id>' (lieu) ou 'v:<id>' (ville).

    Renvoie (lieu_id, ville_id) — au plus un des deux est renseigné.
    """
    val = (val or "").strip()
    if val.startswith("l:"):
        return _int_or_none(val[2:]), None
    if val.startswith("v:"):
        return None, _int_or_none(val[2:])
    return None, None


@config_bp.route("/reglages/tarifs/ajouter", methods=["POST"])
@login_required
def tarif_ajouter():
    prix = _parse_prix(request.form.get("prix"))
    dep_lieu, dep_ville = _parse_endpoint(request.form.get("depart"))
    arr_lieu, arr_ville = _parse_endpoint(request.form.get("arrivee"))
    if prix is None or not (dep_lieu or dep_ville or arr_lieu or arr_ville):
        flash("Choisis au moins un départ ou une arrivée (lieu ou ville) et un "
              "prix valide.", "error")
        return redirect(url_for("config.tarifs"))
    bidir = bool(request.form.get("bidir"))
    C.creer_tarif(prix, dep_lieu, dep_ville, arr_lieu, arr_ville, bidir=bidir)
    flash("Grille tarifaire ajoutée ✓", "success")
    return redirect(url_for("config.tarifs"))


@config_bp.route("/reglages/tarifs/<int:tarif_id>/modifier", methods=["POST"])
@login_required
def tarif_modifier(tarif_id: int):
    prix = _parse_prix(request.form.get("prix"))
    dep_lieu, dep_ville = _parse_endpoint(request.form.get("depart"))
    arr_lieu, arr_ville = _parse_endpoint(request.form.get("arrivee"))
    if prix is None or not (dep_lieu or dep_ville or arr_lieu or arr_ville):
        flash("Choisis au moins un départ ou une arrivée (lieu ou ville) et un "
              "prix valide.", "error")
        return redirect(url_for("config.tarifs"))
    bidir = bool(request.form.get("bidir"))
    C.maj_tarif(tarif_id, prix, dep_lieu, dep_ville, arr_lieu, arr_ville, bidir=bidir)
    flash("Grille tarifaire mise à jour ✓", "success")
    return redirect(url_for("config.tarifs"))


@config_bp.route("/reglages/tarifs/<int:tarif_id>/supprimer", methods=["POST"])
@login_required
def tarif_supprimer(tarif_id: int):
    C.supprimer_tarif(tarif_id)
    flash("Grille tarifaire supprimée.", "info")
    return redirect(url_for("config.tarifs"))


# ── Notifications Web Push (cahier §6.5) — message + test (super-admin) ───────
@config_bp.route("/reglages/notifications")
@super_admin_required
def notifications():
    conducteurs = []
    for c in C.conducteurs_actifs():
        conducteurs.append({
            "id": c["id"],
            "email": label_compte(c),
            "abonne": webpush.compte_a_des_souscriptions(c["id"]),
        })
    return render_template(
        "config_notifications.html",
        titre=notif_title_template(),
        corps=notif_body_template(),
        default_titre=DEFAULT_NOTIF_TITLE,
        default_corps=DEFAULT_NOTIF_BODY,
        placeholders=NOTIF_PLACEHOLDERS,
        conducteurs=conducteurs,
        push_dispo=webpush.is_available(),
        impersonating=bool(session.get("impersonator_id")),
    )


@config_bp.route("/reglages/notifications", methods=["POST"])
@super_admin_required
def notifications_save():
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier ces réglages.", "error")
        return redirect(url_for("config.notifications"))
    if request.form.get("reset"):
        set_setting("push_title_template", "")
        set_setting("push_body_template", "")
        flash("Message de notification réinitialisé.", "info")
        return redirect(url_for("config.notifications"))
    set_setting("push_title_template", (request.form.get("titre") or "").strip())
    set_setting("push_body_template", (request.form.get("corps") or "").strip())
    audit("config_notifications", _acteur())
    flash("Message de notification enregistré ✓", "success")
    return redirect(url_for("config.notifications"))


@config_bp.route("/reglages/notifications/test", methods=["POST"])
@super_admin_required
def notifications_test():
    """Envoie une notification de test à un conducteur (vérifie ses appareils)."""
    cid = _int_or_none(request.form.get("compte_id"))
    cible = None
    for c in C.conducteurs_actifs():
        if c["id"] == cid:
            cible = c
            break
    if cible is None:
        flash("Conducteur introuvable.", "error")
        return redirect(url_for("config.notifications"))
    nom = label_compte(cible)
    if not webpush.is_available():
        flash("Web Push indisponible côté serveur (dépendances manquantes).", "error")
        return redirect(url_for("config.notifications"))
    if not webpush.compte_a_des_souscriptions(cid):
        flash(f"{nom} n'a aucun appareil abonné : il doit d'abord activer les "
              "notifications depuis son calendrier (et, sur iPhone, avoir ajouté "
              "l'app à l'écran d'accueil).", "error")
        return redirect(url_for("config.notifications"))
    n = webpush.notifier_conducteur(
        cid, "Test de notification VTC",
        "Si tu vois ce message, les notifications fonctionnent ✓",
        url=url_for("main.dashboard"))
    if n > 0:
        flash(f"Notification de test envoyée à {nom} ({n} appareil·s) ✓", "success")
    else:
        flash(f"Échec de l'envoi à {nom} (abonnement peut-être périmé).", "error")
    return redirect(url_for("config.notifications"))


# ── Noms d'affichage des conducteurs (table métier vtc_profils) ──────────────
# La base ne stocke que l'e-mail ; ici le super-admin attribue un nom lisible à
# chaque compte (affiché dans l'assignation, le calendrier, les notifications).
@config_bp.route("/reglages/noms")
@super_admin_required
def noms():
    db = get_db()
    rows = db.execute(
        "SELECT c.id, c.email, c.role, p.nom AS nom FROM comptes c "
        "LEFT JOIN vtc_profils p ON p.compte_id = c.id "
        "WHERE c.etat = 'actif' "
        "ORDER BY (c.role = 'super_admin') DESC, COALESCE(p.nom, c.email)"
    ).fetchall()
    return render_template(
        "config_noms.html", comptes=rows,
        impersonating=bool(session.get("impersonator_id")))


@config_bp.route("/reglages/noms/<int:compte_id>", methods=["POST"])
@super_admin_required
def nom_enregistrer(compte_id: int):
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier ces réglages.", "error")
        return redirect(url_for("config.noms"))
    if get_compte(compte_id) is None:
        return redirect(url_for("config.noms"))
    nom = (request.form.get("nom") or "").strip() or None
    C.set_nom_profil(compte_id, nom)
    audit("renommer", _acteur(), cible=f"compte {compte_id}")
    flash("Nom d'affichage mis à jour ✓" if nom else "Nom d'affichage retiré.",
          "success")
    return redirect(url_for("config.noms"))


# ── Estimation de trajet OpenStreetMap : activation (super-admin) ────────────
@config_bp.route("/reglages/estimation", methods=["POST"])
@super_admin_required
def estimation_toggle():
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier ce réglage.", "error")
        return redirect(url_for("accounts.reglages"))
    set_setting("maps_enabled", "1" if request.form.get("maps_enabled") else "0")
    flash("Réglage d'estimation de trajet enregistré.", "success")
    return redirect(url_for("accounts.reglages"))


# ── Villes desservies + Lieux fréquents (cahier §6.2) — tout conducteur actif ─
@config_bp.route("/reglages/lieux")
@login_required
def lieux():
    # Clients + leurs adresses attitrées (affichés en bas de l'écran Lieux).
    clients = []
    for r in C.liste_clients():
        adrs = C.client_adresses(r)
        if adrs:
            clients.append({"id": r["id"], "nom": r["nom"], "adresses_list": adrs})
    return render_template("config_lieux.html",
                           lieux=C.liste_lieux(), villes=C.liste_villes(),
                           clients=clients)


@config_bp.route("/reglages/villes")
@login_required
def villes():
    """Page dédiée : toutes les villes par ordre alphabétique (+ suppression)."""
    return render_template("config_villes.html", villes=C.liste_villes_alpha())


@config_bp.route("/reglages/villes/ajouter", methods=["POST"])
@login_required
def ville_ajouter():
    nom = (request.form.get("nom") or "").strip()
    if not nom:
        flash("Le nom de la ville est requis.", "error")
        return redirect(url_for("config.lieux"))
    C.creer_ville(nom)
    flash("Ville ajoutée ✓", "success")
    return redirect(url_for("config.lieux"))


@config_bp.route("/reglages/villes/ajouter-masse", methods=["POST"])
@login_required
def ville_ajouter_masse():
    noms = (request.form.get("noms") or "").splitlines()
    n = C.ajouter_villes(noms)
    flash(f"{n} ville(s) ajoutée(s) ✓" if n
          else "Aucune nouvelle ville (déjà présentes ?).",
          "success" if n else "info")
    return redirect(url_for("config.lieux"))


@config_bp.route("/reglages/villes/<int:ville_id>/supprimer", methods=["POST"])
@login_required
def ville_supprimer(ville_id: int):
    C.supprimer_ville(ville_id)
    flash("Ville supprimée.", "info")
    # Revient à la page d'où l'on vient (liste des villes, ou écran Lieux).
    ref = request.referrer or ""
    return redirect(url_for("config.villes") if "villes" in ref
                    else url_for("config.lieux"))


@config_bp.route("/reglages/lieux/ajouter", methods=["POST"])
@login_required
def lieu_ajouter():
    nom = (request.form.get("nom") or "").strip()
    adresse = (request.form.get("adresse") or "").strip() or None
    ville_id = _int_or_none(request.form.get("ville_id"))
    if not nom:
        flash("Le nom du lieu est requis.", "error")
        return redirect(url_for("config.lieux"))
    C.creer_lieu(nom, adresse, ville_id)
    flash("Lieu ajouté ✓", "success")
    return redirect(url_for("config.lieux"))


@config_bp.route("/reglages/lieux/<int:lieu_id>/modifier", methods=["POST"])
@login_required
def lieu_modifier(lieu_id: int):
    nom = (request.form.get("nom") or "").strip()
    adresse = (request.form.get("adresse") or "").strip() or None
    ville_id = _int_or_none(request.form.get("ville_id"))
    if not nom:
        flash("Le nom du lieu est requis.", "error")
        return redirect(url_for("config.lieux"))
    C.maj_lieu(lieu_id, nom, adresse, ville_id)
    flash("Lieu mis à jour ✓", "success")
    return redirect(url_for("config.lieux"))


@config_bp.route("/reglages/lieux/<int:lieu_id>/supprimer", methods=["POST"])
@login_required
def lieu_supprimer(lieu_id: int):
    C.supprimer_lieu(lieu_id)
    flash("Lieu supprimé.", "info")
    return redirect(url_for("config.lieux"))


# ── Clients habitués (cahier §6.4) — accessible à tout conducteur actif ──────
@config_bp.route("/clients")
@login_required
def clients():
    rows = []
    for r in C.liste_clients():
        d = dict(r)
        d["adresses_list"] = C.client_adresses(r)
        rows.append(d)
    villes = C.liste_villes()
    return render_template(
        "clients.html", clients=rows, is_super_admin=is_super_admin(),
        villes=villes, villes_noms=[v["nom"] for v in villes])


@config_bp.route("/clients/ajouter", methods=["POST"])
@login_required
def client_ajouter():
    nom = (request.form.get("nom") or "").strip()
    if not nom:
        flash("Le nom du client est requis.", "error")
        return redirect(url_for("config.clients"))
    tel = format_tel(request.form.get("telephone")) or None
    # Vérifie qu'aucun client n'a déjà ce numéro (évite les doublons).
    if tel:
        dup = C.client_par_tel(tel)
        if dup:
            flash(f"Ce numéro est déjà enregistré pour « {dup['nom']} ». "
                  "Client non créé (modifie plutôt la fiche existante).", "error")
            return redirect(url_for("config.clients"))
    adresses = _parse_adresses(request.form)
    notes = (request.form.get("notes") or "").strip() or None
    C.creer_client(nom, tel, adresses, notes)
    flash("Client enregistré ✓", "success")
    return redirect(url_for("config.clients"))


@config_bp.route("/clients/<int:client_id>/modifier", methods=["POST"])
@login_required
def client_modifier(client_id: int):
    nom = (request.form.get("nom") or "").strip()
    if not nom:
        flash("Le nom du client est requis.", "error")
        return redirect(url_for("config.clients"))
    tel = format_tel(request.form.get("telephone")) or None
    if tel:
        dup = C.client_par_tel(tel, exclude_id=client_id)
        if dup:
            flash(f"Ce numéro est déjà enregistré pour « {dup['nom']} ». "
                  "Modification non enregistrée.", "error")
            return redirect(url_for("config.clients"))
    adresses = _parse_adresses(request.form)
    notes = (request.form.get("notes") or "").strip() or None
    C.maj_client(client_id, nom, tel, adresses, notes)
    flash("Client mis à jour ✓", "success")
    return redirect(url_for("config.clients"))


@config_bp.route("/clients/<int:client_id>/supprimer", methods=["POST"])
@login_required
def client_supprimer(client_id: int):
    C.supprimer_client(client_id)
    flash("Client supprimé.", "info")
    return redirect(url_for("config.clients"))


def _parse_prix(v):
    v = (v or "").strip().replace(",", ".")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_adresses(form):
    """Lit les adresses habituelles d'un client depuis le formulaire.

    Format courant : champ caché `adresses_json` = liste JSON de
    {label, adresse}. Repli historique : `adresses` = une adresse par ligne.
    Renvoie une liste normalisée de dicts {label, adresse} (vides ignorés).
    """
    import json as _json
    raw = form.get("adresses_json")
    if raw:
        try:
            data = _json.loads(raw)
        except (ValueError, TypeError):
            data = []
        return C._normaliser_adresses(data)
    # Repli : ancien textarea (une adresse par ligne, sans libellé).
    lignes = [l.strip() for l in (form.get("adresses") or "").splitlines() if l.strip()]
    return C._normaliser_adresses(lignes)
