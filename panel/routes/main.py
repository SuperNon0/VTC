"""Écrans métier taxi/VTC : calendrier du conducteur, création de course,
courses créées, statistiques (stub) et endpoints associés.

Toute la logique d'affichage se base sur le **conducteur assigné** (cahier §5).
Le compte super_admin est traité exactement comme un conducteur pour son propre
calendrier et ses stats (cahier §3) ; la vue « mes stats » est unique et
réutilisée par le super-admin via « voir en tant que » (impersonation, §6.7).
"""

from __future__ import annotations

from datetime import datetime

from flask import (Blueprint, Response, abort, flash, jsonify, redirect,
                   render_template, request, url_for)

from .. import courses as C
from .. import maps
from .. import webpush
from ..ai import AIError, extract_course_info, is_configured as ai_configured
from ..auth import current_compte, is_super_admin, login_required
from ..utils import course_ics, fmt_dt, google_calendar_url

bp = Blueprint("main", __name__)


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
            label = fmt_dt(ts, with_time=False) if ts else "Sans date"
            groupes.append({"jour": jour, "label": label, "courses": []})
        groupes[-1]["courses"].append(_course_view(row))
    return groupes


# ─────────────────────────────────────────────────────────────────────────────
# Calendrier personnel (dashboard) — cahier §6.6
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/")
@login_required
def dashboard():
    compte = current_compte()
    rows = C.courses_assignees(compte["id"], a_venir=True)
    return render_template(
        "dashboard.html",
        compte=compte,
        is_super_admin=is_super_admin(),
        groupes=_grouper_par_jour(rows),
        total=len(rows),
        push_available=webpush.is_available(),
        deja_abonne=webpush.compte_a_des_souscriptions(compte["id"]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Détail d'une course (page ouverte au clic sur un événement du calendrier)
# Affiche toutes les infos ; le statut se met à jour ICI (dans l'app), pas
# depuis l'événement figé exporté vers le calendrier natif iPhone/Android.
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/course/<int:course_id>")
@login_required
def course_detail(course_id: int):
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        abort(404)
    if compte["id"] not in (course["conducteur_id"], course["createur_id"]):
        abort(403)
    from ..db import get_db
    from ..utils import label_compte
    db = get_db()
    cond = db.execute("SELECT email, nom, role FROM comptes WHERE id = ?",
                      (course["conducteur_id"],)).fetchone()
    crea = db.execute("SELECT email, nom, role FROM comptes WHERE id = ?",
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


@bp.post("/course/<int:course_id>/supprimer")
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


@bp.post("/course/<int:course_id>/estimer")
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
@bp.route("/nouvelle")
@login_required
def nouvelle_course():
    compte = current_compte()
    lieux = C.liste_lieux()
    tarifs = C.liste_tarifs()
    return render_template(
        "nouvelle_course.html",
        compte=compte,
        is_super_admin=is_super_admin(),
        conducteurs=C.conducteurs_actifs(),
        lieux=lieux,
        tarifs=tarifs,
        # Données pour l'autocomplétion des lieux + l'auto-sélection du tarif.
        lieux_json=[{"id": l["id"], "nom": l["nom"], "adresse": l["adresse"] or ""}
                    for l in lieux],
        tarifs_json=[{"id": t["id"], "prix": t["prix"],
                      "dep": t["lieu_depart_id"], "arr": t["lieu_arrivee_id"]}
                     for t in tarifs],
        ai_on=ai_configured(),
    )


@bp.post("/api/extract")
@login_required
def api_extract():
    """Extraction IA des infos client depuis un message brut (cahier §6.1)."""
    data = request.get_json(silent=True) or {}
    try:
        infos = extract_course_info(data.get("message", ""))
    except AIError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return jsonify(ok=True, infos=infos)


@bp.post("/api/courses")
@login_required
def api_creer_course():
    """Crée une course, l'assigne, et notifie le conducteur assigné (§6.5)."""
    compte = current_compte()
    f = request.form

    # Conducteur assigné : obligatoire, doit être actif.
    try:
        conducteur_id = int(f.get("conducteur_id", ""))
    except (TypeError, ValueError):
        conducteur_id = 0
    valides = {c["id"] for c in C.conducteurs_actifs()}
    if conducteur_id not in valides:
        flash("Choisis un conducteur assigné valide.", "error")
        return redirect(url_for("main.nouvelle_course"))

    # Date et heure : deux champs séparés → timestamp. L'heure vide vaut 00:00.
    # (Rétrocompatible avec un ancien champ combiné « quand ».)
    date_str = (f.get("date") or "").strip()
    heure_str = (f.get("heure") or "").strip() or "00:00"
    if date_str:
        quand = _parse_datetime_local(f"{date_str}T{heure_str}")
    else:
        quand = _parse_datetime_local(f.get("quand", ""))
    if quand is None:
        flash("Renseigne au moins une date valide.", "error")
        return redirect(url_for("main.nouvelle_course"))

    # Prix : soit une grille tarifaire, soit « Autre » (prix libre) — cahier §6.3.
    prix, prix_source, tarif_id = _resoudre_prix(f)

    depart = (f.get("depart") or "").strip() or None
    arrivee = (f.get("arrivee") or "").strip() or None

    # Estimation du trajet (durée + distance) via OpenStreetMap — best-effort.
    distance_km = duree_min = None
    if depart and arrivee:
        est = maps.estimate(depart, arrivee)
        if est:
            distance_km, duree_min = est["distance_km"], est["duree_min"]

    data = {
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
        "statut": "a_faire",
        "conducteur_id": conducteur_id,
        "client_id": _int_or_none(f.get("client_id")),
        "notes": (f.get("notes") or "").strip() or None,
    }
    course_id = C.creer_course(data, compte["id"])

    # Notification push au conducteur assigné (jamais au créateur) — cahier §5/§6.5.
    # Titre + corps personnalisables (Paramètres → Notifications, super-admin).
    # Le clic sur la notification ouvre directement la course concernée.
    from ..utils import notif_titre, notif_corps
    webpush.notifier_conducteur(
        conducteur_id, notif_titre(data), notif_corps(data),
        url=url_for("main.course_detail", course_id=course_id),
    )
    flash("Course créée et assignée ✓", "success")
    return redirect(url_for("main.dashboard"))


# ─────────────────────────────────────────────────────────────────────────────
# Courses que j'ai créées (vue créateur, distincte du calendrier) — cahier §5
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/plus")
@login_required
def plus():
    """Menu « Plus » : accès secondaires (stats, lieux, paramètres, déconnexion)."""
    return render_template(
        "plus.html", compte=current_compte(), is_super_admin=is_super_admin())


@bp.route("/mes-courses")
@login_required
def mes_courses():
    compte = current_compte()
    rows = [_course_view(r) for r in C.courses_creees(compte["id"])]
    return render_template(
        "mes_courses.html", compte=compte,
        is_super_admin=is_super_admin(), courses=rows,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mes statistiques — vue unique réutilisée par l'impersonation (cahier §6.7)
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/mes-stats")
@login_required
def mes_stats():
    """Tableau de bord personnel du conducteur effectif.

    Fonctionnalité **différée** (cahier §6.7) : on n'affiche qu'un aperçu à
    partir des données déjà stockées (date, prix, statut, conducteur assigné),
    volontairement requêtables par conducteur/période. Le super-admin consulte
    les stats d'un conducteur via « voir en tant que » — aucune vue séparée.
    """
    compte = current_compte()
    apercu = _apercu_stats(compte["id"])
    return render_template(
        "mes_stats.html", compte=compte,
        is_super_admin=is_super_admin(), apercu=apercu,
    )


def _apercu_stats(conducteur_id: int) -> dict:
    """Agrégat minimal du mois en cours (structure prête, détail à venir §6.7)."""
    from ..db import get_db
    now = datetime.now()
    debut_mois = int(datetime(now.year, now.month, 1).timestamp())
    row = get_db().execute(
        "SELECT COUNT(*) AS n, "
        "COALESCE(SUM(CASE WHEN statut = 'terminee' THEN prix END), 0) AS ca "
        "FROM courses WHERE conducteur_id = ? AND quand >= ? AND statut != 'annulee'",
        (conducteur_id, debut_mois),
    ).fetchone()
    return {"mois": now.strftime("%m/%Y"), "nb_courses": row["n"], "ca": row["ca"]}


# ─────────────────────────────────────────────────────────────────────────────
# Statut d'une course (le conducteur assigné avance son statut)
# ─────────────────────────────────────────────────────────────────────────────
@bp.post("/api/courses/<int:course_id>/statut")
@login_required
def api_statut(course_id: int):
    compte = current_compte()
    course = C.get_course(course_id)
    if course is None:
        return jsonify(ok=False, error="introuvable"), 404
    # Seul le conducteur assigné (ou le créateur) peut changer le statut.
    if compte["id"] not in (course["conducteur_id"], course["createur_id"]):
        return jsonify(ok=False, error="non autorisé"), 403
    statut = (request.form.get("statut") or "").strip()
    if not C.set_statut(course_id, statut):
        return jsonify(ok=False, error="statut invalide"), 400
    return jsonify(ok=True, statut=statut, label=C.STATUT_LABELS.get(statut))


# ─────────────────────────────────────────────────────────────────────────────
# Clients — autocomplétion (cahier §6.4)
# ─────────────────────────────────────────────────────────────────────────────
@bp.get("/api/clients/search")
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
            "adresses": C.client_adresses(row),
        })
    return jsonify(clients=out)


# ─────────────────────────────────────────────────────────────────────────────
# Export calendrier natif (cahier §6.6)
# ─────────────────────────────────────────────────────────────────────────────
@bp.get("/course/<int:course_id>/ics")
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


@bp.get("/course/<int:course_id>/google")
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
@bp.get("/api/push/key")
@login_required
def api_push_key():
    return jsonify(key=webpush.public_key(), available=webpush.is_available())


@bp.post("/api/push/subscribe")
@login_required
def api_push_subscribe():
    compte = current_compte()
    sub = request.get_json(silent=True) or {}
    ok = webpush.enregistrer_souscription(
        compte["id"], sub, request.headers.get("User-Agent"))
    return (jsonify(ok=True) if ok
            else (jsonify(ok=False, error="souscription invalide"), 400))


@bp.post("/api/push/unsubscribe")
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
@bp.get("/sw.js")
def service_worker():
    from flask import current_app
    resp = current_app.send_static_file("sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privés
# ─────────────────────────────────────────────────────────────────────────────
def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_datetime_local(value: str):
    """Convertit un champ <input type=datetime-local> en timestamp Unix."""
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
    # « Autre » : prix libre.
    prix_libre = (f.get("prix_libre") or "").strip().replace(",", ".")
    try:
        return (float(prix_libre) if prix_libre else None), "autre", None
    except ValueError:
        return None, "autre", None
