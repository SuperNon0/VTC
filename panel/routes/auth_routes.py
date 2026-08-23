"""Parcours de connexion : gateway (arbre de décision), login local, demande.

Conforme à docs/authentification-v2.md §4 (détection du canal + arbre de
décision) et §2 (machine à états).
"""

from __future__ import annotations

import time

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

from ..auth import cf_access_email, login_compte
from ..db import audit, get_db
from ..notify import notify
from ..utils import fmt_dt

bp = Blueprint("auth", __name__)


def _compte_par_email(email: str):
    return get_db().execute("SELECT * FROM comptes WHERE email = ?", (email,)).fetchone()


@bp.route("/gateway")
def gateway():
    """Point d'entrée : décide quelle page présenter selon le canal + l'état.

    - Pas d'e-mail Cloudflare (accès LAN) → login local par mot de passe.
    - E-mail Cloudflare présent → arbre de décision selon l'état du compte.
    """
    email = cf_access_email()

    # --- Accès local / LAN : pas d'en-tête Cloudflare ---
    if email is None:
        if not current_app.config.get("ALLOW_LOCAL_LOGIN", True):
            return render_template("bloque.html", email="—"), 403
        return render_template("login.html")

    # --- Accès via Cloudflare : e-mail vérifié ---
    compte = _compte_par_email(email)
    if compte is None:
        return render_template("demande.html", email=email)

    etat = compte["etat"]
    if etat == "pending":
        return render_template("attente.html", email=email,
                               demande_le=fmt_dt(compte["cree"]))
    if etat == "refused":
        return render_template("refus.html", email=email)
    if etat == "bloque":
        return render_template("bloque.html", email=email)

    # actif → ouvre la session et entre dans l'app
    login_compte(compte)
    return redirect(url_for("main.dashboard"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Login local par mot de passe (super-admin, accès LAN uniquement)."""
    # Un accès direct en GET (rechargement, historique, redirection) renvoie
    # proprement vers la page de connexion au lieu d'un 405.
    if request.method == "GET":
        return redirect(url_for("auth.gateway"))
    # Sécurité : si Cloudflare a authentifié un e-mail, on n'utilise pas ce chemin.
    if cf_access_email() is not None:
        return redirect(url_for("auth.gateway"))

    time.sleep(1)  # anti-force brute (spec §9.5)
    password = request.form.get("password", "")
    db = get_db()
    row = db.execute(
        "SELECT * FROM comptes WHERE role = 'super_admin' AND mdp_hash IS NOT NULL "
        "ORDER BY id LIMIT 1"
    ).fetchone()

    if row is None or not check_password_hash(row["mdp_hash"], password):
        flash("Mot de passe incorrect.", "error")
        return redirect(url_for("auth.gateway"))

    if row["etat"] != "actif":
        return render_template("bloque.html", email=row["email"] or "—")

    login_compte(row)
    audit("login_local", acteur=row["email"] or "super_admin")
    return redirect(url_for("main.dashboard"))


@bp.route("/request-access", methods=["POST"])
def request_access():
    """Crée (ou recrée) une demande `pending` pour l'e-mail Cloudflare courant."""
    email = cf_access_email()
    if email is None:
        return redirect(url_for("auth.gateway"))

    db = get_db()
    compte = _compte_par_email(email)
    now = int(time.time())

    if compte is None:
        db.execute(
            "INSERT INTO comptes (email, role, etat, cree) VALUES (?, 'membre', 'pending', ?)",
            (email, now),
        )
    elif compte["etat"] == "refused":
        # « Redemander un accès » : refused → pending
        db.execute("UPDATE comptes SET etat = 'pending', cree = ? WHERE id = ?",
                   (now, compte["id"]))
    else:
        return redirect(url_for("auth.gateway"))
    db.commit()

    audit("demande_acces", acteur=email, cible=email)
    notify(current_app.config["NOTIFY_SLUG_ACCESS_REQUEST"], email=email)
    return redirect(url_for("auth.gateway"))


@bp.route("/mot-de-passe-oublie")
def forgot():
    """Explique comment réinitialiser le mot de passe super-admin (commande serveur).

    Le reset se fait côté serveur (accès shell) et ne dépend donc pas d'être
    connecté — voir panel/reset_admin.py et deploy/reset_admin.sh.
    """
    return render_template("oubli.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.gateway"))
