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
from .helpers import (CAL_PLACEHOLDERS, DEFAULT_CAL_NOTES, DEFAULT_CAL_TITLE,
                      NOTIF_PLACEHOLDERS, DEFAULT_NOTIF_BODY,
                      DEFAULT_NOTIF_TITLE, cal_notes_template,
                      cal_title_template, course_ics, fmt_dt,
                      google_calendar_url, label_compte, notif_body_template,
                      notif_corps, notif_title_template, notif_titre)

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
            label = fmt_dt(ts, with_time=False) if ts else "Sans date"
            groupes.append({"jour": jour, "label": label, "courses": []})
        groupes[-1]["courses"].append(_course_view(row))
    return groupes


# ─────────────────────────────────────────────────────────────────────────────
# Calendrier personnel (dashboard / accueil) — cahier §6.6
# ─────────────────────────────────────────────────────────────────────────────
@main_bp.route("/")
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
    rows = [_course_view(r) for r in C.courses_creees(compte["id"])]
    return render_template(
        "mes_courses.html", compte=compte,
        is_super_admin=is_super_admin(), courses=rows,
    )


@main_bp.route("/mes-stats")
@login_required
def mes_stats():
    """Tableau de bord personnel du conducteur effectif (cahier §6.7)."""
    compte = current_compte()
    apercu = _apercu_stats(compte["id"])
    return render_template(
        "mes_stats.html", compte=compte,
        is_super_admin=is_super_admin(), apercu=apercu,
    )


def _apercu_stats(conducteur_id: int) -> dict:
    """Agrégat minimal du mois en cours (structure prête, détail à venir §6.7)."""
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
    tel = (request.form.get("telephone") or "").strip() or None
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
    tel = (request.form.get("telephone") or "").strip() or None
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
