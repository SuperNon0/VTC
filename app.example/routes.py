"""Écrans du projet (exemple). Tu réutilises la base sans la modifier.

- `login_required` / `super_admin_required` viennent de la base (`panel.auth`).
- Le thème et le layout `base.html` viennent de la base : `{% extends "base.html" %}`.
- Les données par utilisateur : filtre par le compte *effectif* (impersonation
  incluse) → `current_compte()["id"]`.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from panel.auth import current_compte, is_super_admin, login_required
from panel.db import get_db
from panel.settings import get_setting, set_setting

bp = Blueprint("app", __name__)


@bp.app_context_processor
def _reglages_ctx():
    """Expose les réglages de l'app aux templates (dont le partial app_reglages.html
    inclus par la page /reglages de la base)."""
    return {"app_titre": get_setting("app_titre", "")}


@bp.route("/")
@login_required
def dashboard():
    """Écran d'accueil du projet — remplace la démo de la base."""
    compte = current_compte()
    # Exemple : compter les éléments de CE compte (données cloisonnées).
    n = get_db().execute(
        "SELECT COUNT(*) FROM exemple_items WHERE compte_id = ?", (compte["id"],)
    ).fetchone()[0]
    return render_template("dashboard.html", compte=compte,
                           is_super_admin=is_super_admin(), nb_items=n,
                           app_titre=get_setting("app_titre", ""))


@bp.route("/reglages/enregistrer", methods=["POST"])
@login_required
def reglages_enregistrer():
    """Enregistre un réglage de l'application (exemple).

    On réutilise le magasin clé/valeur de la base (`app_settings`) via
    `set_setting` : pas besoin de table dédiée pour de simples options. La page
    /reglages (base) inclut le partial `app_reglages.html` déclaré dans __init__.
    """
    set_setting("app_titre", (request.form.get("app_titre") or "").strip())
    flash("Réglages de l'application enregistrés.", "success")
    return redirect(url_for("accounts.reglages"))
