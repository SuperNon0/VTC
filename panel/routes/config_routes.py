"""Réglages métier taxi/VTC :

  - Extraction IA (fournisseur + clé + modèle) — super-admin (cahier §6.1)
  - Grilles tarifaires                          — super-admin (cahier §6.3)
  - Lieux fréquents                             — tout conducteur actif (§6.2)
  - Clients habitués                            — tout conducteur actif (§6.4)

Les réglages IA/VAPID/… sont stockés dans `app_settings` (clé/valeur), comme la
config Cloudflare existante : le super-admin bascule de fournisseur sans repasser
par le développement (cahier §6.1).
"""

from __future__ import annotations

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from .. import courses as C
from ..ai import DEFAULTS, PROVIDER_LABELS, PROVIDERS, ai_config
from ..auth import (get_compte, is_super_admin, login_required,
                    super_admin_required)
from ..db import audit
from ..settings import set_setting
from ..utils import (CAL_PLACEHOLDERS, DEFAULT_CAL_NOTES, DEFAULT_CAL_TITLE,
                     cal_notes_template, cal_title_template)

bp = Blueprint("config", __name__)


def _acteur() -> str:
    c = get_compte(session.get("impersonator_id") or session.get("compte_id"))
    return (c["email"] if c and c["email"] else "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# Extraction IA (cahier §6.1) — super-admin uniquement
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/parametres/ia")
@super_admin_required
def ia():
    cfg = ai_config()
    return render_template(
        "config_ia.html",
        providers=PROVIDER_LABELS,
        defaults=DEFAULTS,
        cfg=cfg,
        impersonating=bool(session.get("impersonator_id")),
    )


@bp.route("/parametres/ia", methods=["POST"])
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
    # Ne réécrit pas la clé si le champ est laissé vide (elle est masquée à l'écran).
    if key:
        set_setting("ai_api_key", key)
    elif request.form.get("clear_key"):
        set_setting("ai_api_key", "")

    audit("config_ia", _acteur(), detail=f"provider={provider} model={model}")
    flash("Réglages d'extraction IA enregistrés.", "success")
    return redirect(url_for("config.ia"))


# ─────────────────────────────────────────────────────────────────────────────
# Modèle d'export calendrier (cahier §6.6) — super-admin uniquement
# Titre + notes de l'événement, personnalisables avec des [placeholders].
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/parametres/calendrier")
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


@bp.route("/parametres/calendrier", methods=["POST"])
@super_admin_required
def calendrier_save():
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier ces réglages.", "error")
        return redirect(url_for("config.calendrier"))
    # Si on réinitialise, on efface les réglages → les valeurs par défaut reviennent.
    if request.form.get("reset"):
        set_setting("cal_title_template", "")
        set_setting("cal_notes_template", "")
        flash("Modèle de calendrier réinitialisé aux valeurs par défaut.", "info")
        return redirect(url_for("config.calendrier"))
    titre = (request.form.get("titre") or "").strip()
    notes = (request.form.get("notes") or "").rstrip()
    set_setting("cal_title_template", titre)
    set_setting("cal_notes_template", notes)
    audit("config_calendrier", _acteur())
    flash("Modèle d'export calendrier enregistré ✓", "success")
    return redirect(url_for("config.calendrier"))


# ─────────────────────────────────────────────────────────────────────────────
# Grilles tarifaires (cahier §6.3) — super-admin uniquement
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/parametres/tarifs")
@super_admin_required
def tarifs():
    return render_template("config_tarifs.html",
                           tarifs=C.liste_tarifs(), lieux=C.liste_lieux())


@bp.route("/parametres/tarifs/ajouter", methods=["POST"])
@super_admin_required
def tarif_ajouter():
    prix = _parse_prix(request.form.get("prix"))
    dep = _int_or_none(request.form.get("lieu_depart_id"))
    arr = _int_or_none(request.form.get("lieu_arrivee_id"))
    if prix is None or (dep is None and arr is None):
        flash("Choisis au moins un lieu (départ et/ou arrivée) et un prix valide.",
              "error")
        return redirect(url_for("config.tarifs"))
    C.creer_tarif(prix, dep, arr)
    flash("Grille tarifaire ajoutée ✓", "success")
    return redirect(url_for("config.tarifs"))


@bp.route("/parametres/tarifs/<int:tarif_id>/modifier", methods=["POST"])
@super_admin_required
def tarif_modifier(tarif_id: int):
    prix = _parse_prix(request.form.get("prix"))
    dep = _int_or_none(request.form.get("lieu_depart_id"))
    arr = _int_or_none(request.form.get("lieu_arrivee_id"))
    if prix is None or (dep is None and arr is None):
        flash("Choisis au moins un lieu (départ et/ou arrivée) et un prix valide.",
              "error")
        return redirect(url_for("config.tarifs"))
    C.maj_tarif(tarif_id, prix, dep, arr)
    flash("Grille tarifaire mise à jour ✓", "success")
    return redirect(url_for("config.tarifs"))


@bp.route("/parametres/tarifs/<int:tarif_id>/supprimer", methods=["POST"])
@super_admin_required
def tarif_supprimer(tarif_id: int):
    C.supprimer_tarif(tarif_id)
    flash("Grille tarifaire supprimée.", "info")
    return redirect(url_for("config.tarifs"))


@bp.route("/parametres/estimation", methods=["POST"])
@super_admin_required
def estimation_toggle():
    """Active/désactive l'estimation de trajet OpenStreetMap (super-admin)."""
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier ce réglage.", "error")
        return redirect(url_for("accounts.parametres"))
    set_setting("maps_enabled", "1" if request.form.get("maps_enabled") else "0")
    flash("Réglage d'estimation de trajet enregistré.", "success")
    return redirect(url_for("accounts.parametres"))


# ─────────────────────────────────────────────────────────────────────────────
# Lieux fréquents (cahier §6.2) — gérables par TOUT conducteur actif.
# La liste se construit au fur et à mesure : chaque conducteur peut ajouter ou
# retirer un lieu (choix du propriétaire : liste collaborative, pas réservée au
# super-admin).
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/parametres/lieux")
@login_required
def lieux():
    return render_template("config_lieux.html", lieux=C.liste_lieux())


@bp.route("/parametres/lieux/ajouter", methods=["POST"])
@login_required
def lieu_ajouter():
    nom = (request.form.get("nom") or "").strip()
    adresse = (request.form.get("adresse") or "").strip() or None
    if not nom:
        flash("Le nom du lieu est requis.", "error")
        return redirect(url_for("config.lieux"))
    C.creer_lieu(nom, adresse)
    flash("Lieu ajouté ✓", "success")
    return redirect(url_for("config.lieux"))


@bp.route("/parametres/lieux/<int:lieu_id>/supprimer", methods=["POST"])
@login_required
def lieu_supprimer(lieu_id: int):
    C.supprimer_lieu(lieu_id)
    flash("Lieu supprimé.", "info")
    return redirect(url_for("config.lieux"))


# ─────────────────────────────────────────────────────────────────────────────
# Clients habitués (cahier §6.4) — accessible à tout conducteur actif
# ─────────────────────────────────────────────────────────────────────────────
@bp.route("/clients")
@login_required
def clients():
    rows = []
    for r in C.liste_clients():
        d = dict(r)
        d["adresses_list"] = C.client_adresses(r)
        rows.append(d)
    return render_template(
        "clients.html", clients=rows, is_super_admin=is_super_admin())


@bp.route("/clients/ajouter", methods=["POST"])
@login_required
def client_ajouter():
    nom = (request.form.get("nom") or "").strip()
    if not nom:
        flash("Le nom du client est requis.", "error")
        return redirect(url_for("config.clients"))
    tel = (request.form.get("telephone") or "").strip() or None
    adresses = _split_adresses(request.form.get("adresses"))
    notes = (request.form.get("notes") or "").strip() or None
    C.creer_client(nom, tel, adresses, notes)
    flash("Client enregistré ✓", "success")
    return redirect(url_for("config.clients"))


@bp.route("/clients/<int:client_id>/modifier", methods=["POST"])
@login_required
def client_modifier(client_id: int):
    nom = (request.form.get("nom") or "").strip()
    if not nom:
        flash("Le nom du client est requis.", "error")
        return redirect(url_for("config.clients"))
    tel = (request.form.get("telephone") or "").strip() or None
    adresses = _split_adresses(request.form.get("adresses"))
    notes = (request.form.get("notes") or "").strip() or None
    C.maj_client(client_id, nom, tel, adresses, notes)
    flash("Client mis à jour ✓", "success")
    return redirect(url_for("config.clients"))


@bp.route("/clients/<int:client_id>/supprimer", methods=["POST"])
@login_required
def client_supprimer(client_id: int):
    C.supprimer_client(client_id)
    flash("Client supprimé.", "info")
    return redirect(url_for("config.clients"))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _parse_prix(v):
    v = (v or "").strip().replace(",", ".")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _split_adresses(v):
    """Une adresse par ligne dans le textarea."""
    return [line.strip() for line in (v or "").splitlines() if line.strip()]
