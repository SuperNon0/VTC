"""Gestion des comptes (Paramètres → Comptes) + impersonation.

Conforme à docs/authentification-v2.md §5 (gestion), §6 (voir en tant que) et
§8 (endpoints). Les formulaires HTML n'acceptant que GET/POST, toutes les
actions sont en POST (la spec §8 les décrit en verbes REST — même effet).
"""

from __future__ import annotations

import time

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import (cf_diagnostic, current_compte, get_compte, is_super_admin,
                    login_required, reset_jwk_cache, super_admin_required)
from ..db import audit, get_db
from ..notify import notify
from ..settings import cf_config, set_setting
from ..utils import fmt_dt

bp = Blueprint("accounts", __name__)

MIN_MDP_LEN = 8


def _row_to_view(row) -> dict:
    d = dict(row)
    d["cree_fmt"] = fmt_dt(row["cree"], with_time=False)
    d["derniere_cnx_fmt"] = fmt_dt(row["derniere_cnx"])
    d["bloque_fmt"] = fmt_dt(row["bloque"], with_time=False)
    return d


@bp.route("/parametres/comptes")
@super_admin_required
def comptes():
    db = get_db()
    pending = [_row_to_view(r) for r in db.execute(
        "SELECT * FROM comptes WHERE etat = 'pending' ORDER BY cree DESC").fetchall()]
    membres = [_row_to_view(r) for r in db.execute(
        "SELECT * FROM comptes WHERE etat IN ('actif', 'bloque') "
        "ORDER BY (role = 'super_admin') DESC, email").fetchall()]
    # id du super-admin réel (même en impersonation) pour marquer « toi ».
    moi_id = session.get("impersonator_id") or session.get("compte_id")
    return render_template("comptes.html", pending=pending, membres=membres, moi_id=moi_id)


def _acteur() -> str:
    c = get_compte(session.get("impersonator_id") or session.get("compte_id"))
    return (c["email"] if c and c["email"] else "super_admin")


# ── Paramètres : mot de passe administrateur ────────────────────────────────
@bp.route("/parametres")
@super_admin_required
def parametres():
    # Compte super-admin réel (jamais l'identité impersonnée).
    moi = get_compte(session.get("impersonator_id") or session.get("compte_id"))
    return render_template(
        "parametres.html",
        has_password=bool(moi and moi["mdp_hash"]),
        impersonating=bool(session.get("impersonator_id")),
        cf=cf_config(),
        diag=cf_diagnostic(),
    )


@bp.route("/parametres/cloudflare", methods=["POST"])
@super_admin_required
def cloudflare_settings():
    """Enregistre la config Cloudflare Zero Trust depuis l'UI (spec §9.1)."""
    if session.get("impersonator_id"):
        flash("Reviens à ton compte pour modifier les réglages.", "error")
        return redirect(url_for("accounts.parametres"))
    team = request.form.get("cf_team", "").strip()
    aud = request.form.get("cf_aud", "").strip()
    verify = "1" if request.form.get("cf_verify") else "0"
    if verify == "1" and (not team or not aud):
        flash("Renseigne l'équipe ET l'AUD avant d'activer la vérification.", "error")
        return redirect(url_for("accounts.parametres"))
    set_setting("cf_team_domain", team)
    set_setting("cf_aud", aud)
    set_setting("cf_verify_jwt", verify)
    reset_jwk_cache()
    audit("config_cloudflare", _acteur(), detail=f"team={team} verify={verify}")
    flash("Réglages Cloudflare enregistrés.", "success")
    return redirect(url_for("accounts.parametres"))


@bp.route("/parametres/update", methods=["POST"])
@super_admin_required
def update_app():
    """Met à jour le hub depuis GitHub (git pull + deps) puis recharge.

    Le service tourne sous l'utilisateur propriétaire du dépôt : il fait donc
    lui-même le pull et l'install (sans sudo), et remonte l'erreur exacte en cas
    d'échec. Le rechargement du code se fait par un signal à gunicorn (SIGHUP),
    sans sudo ni systemctl.
    """
    import os
    import signal
    import subprocess
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pip = os.path.join(repo, ".venv", "bin", "pip")

    try:
        pull = subprocess.run(["git", "-C", repo, "pull", "--ff-only"],
                              capture_output=True, text=True, timeout=90)
    except Exception as exc:
        flash(f"Échec de git : {exc}", "error")
        return redirect(url_for("accounts.parametres"))
    if pull.returncode != 0:
        flash("git pull a échoué : " + (pull.stderr or pull.stdout).strip()[:400], "error")
        return redirect(url_for("accounts.parametres"))
    if "Already up to date" in pull.stdout or "Déjà à jour" in pull.stdout:
        flash("Déjà à jour ✓", "info")
        return redirect(url_for("accounts.parametres"))

    if os.path.exists(pip):
        pipr = subprocess.run([pip, "install", "-q", "-r", os.path.join(repo, "requirements.txt")],
                              capture_output=True, text=True, timeout=300)
        if pipr.returncode != 0:
            flash("Code récupéré mais l'install des dépendances a échoué : "
                  + pipr.stderr.strip()[:300], "error")
            return redirect(url_for("accounts.parametres"))

    audit("update_app", _acteur())

    # Rechargement du code sans sudo : SIGHUP au master gunicorn.
    if "gunicorn" in request.environ.get("SERVER_SOFTWARE", "").lower():
        try:
            os.kill(os.getppid(), signal.SIGHUP)
            flash("Mis à jour et rechargé ✓ — recharge la page dans ~10 s.", "success")
            return redirect(url_for("accounts.parametres"))
        except Exception:
            pass
    flash("Code mis à jour ✓ — redémarre le service pour l'appliquer "
          "(systemctl restart site-base).", "success")
    return redirect(url_for("accounts.parametres"))


@bp.route("/parametres/mot-de-passe", methods=["POST"])
@super_admin_required
def changer_mdp():
    # Interdit pendant une impersonation (on ne change pas le mdp d'un autre).
    if session.get("impersonator_id"):
        flash("Reviens à ton compte avant de changer le mot de passe.", "error")
        return redirect(url_for("accounts.parametres"))

    db = get_db()
    moi = get_compte(session.get("compte_id"))
    actuel = request.form.get("actuel", "")
    nouveau = request.form.get("nouveau", "")
    confirme = request.form.get("confirme", "")

    # Si un mot de passe existe déjà, il faut fournir l'actuel.
    if moi["mdp_hash"] and not check_password_hash(moi["mdp_hash"], actuel):
        flash("Mot de passe actuel incorrect.", "error")
        return redirect(url_for("accounts.parametres"))
    if len(nouveau) < MIN_MDP_LEN:
        flash(f"Le nouveau mot de passe doit faire au moins {MIN_MDP_LEN} caractères.", "error")
        return redirect(url_for("accounts.parametres"))
    if nouveau != confirme:
        flash("La confirmation ne correspond pas.", "error")
        return redirect(url_for("accounts.parametres"))

    db.execute("UPDATE comptes SET mdp_hash = ? WHERE id = ?",
               (generate_password_hash(nouveau), moi["id"]))
    db.commit()
    audit("changer_mdp", _acteur())
    flash("Mot de passe administrateur mis à jour.", "success")
    return redirect(url_for("accounts.parametres"))


@bp.route("/api/comptes/<int:compte_id>/valider", methods=["POST"])
@super_admin_required
def valider(compte_id: int):
    db = get_db()
    c = get_compte(compte_id)
    if c and c["etat"] == "pending":
        db.execute("UPDATE comptes SET etat = 'actif', valide = ? WHERE id = ?",
                   (int(time.time()), compte_id))
        db.commit()
        audit("valider", _acteur(), c["email"])
        notify(current_app.config["NOTIFY_SLUG_ACCESS_VALIDATED"], email=c["email"])
        flash(f"{c['email']} a été validé.", "success")
    return redirect(url_for("accounts.comptes"))


@bp.route("/api/comptes/<int:compte_id>/refuser", methods=["POST"])
@super_admin_required
def refuser(compte_id: int):
    db = get_db()
    c = get_compte(compte_id)
    if c and c["etat"] == "pending":
        db.execute("UPDATE comptes SET etat = 'refused' WHERE id = ?", (compte_id,))
        db.commit()
        audit("refuser", _acteur(), c["email"])
        flash(f"Demande de {c['email']} refusée.", "info")
    return redirect(url_for("accounts.comptes"))


@bp.route("/api/comptes/<int:compte_id>/bloquer", methods=["POST"])
@super_admin_required
def bloquer(compte_id: int):
    db = get_db()
    c = get_compte(compte_id)
    if c and c["role"] != "super_admin" and c["etat"] == "actif":
        db.execute("UPDATE comptes SET etat = 'bloque', bloque = ? WHERE id = ?",
                   (int(time.time()), compte_id))
        db.commit()
        audit("bloquer", _acteur(), c["email"])
        notify(current_app.config["NOTIFY_SLUG_ACCESS_BLOCKED"], email=c["email"])
        flash(f"{c['email']} a été bloqué.", "info")
    return redirect(url_for("accounts.comptes"))


@bp.route("/api/comptes/<int:compte_id>/debloquer", methods=["POST"])
@super_admin_required
def debloquer(compte_id: int):
    db = get_db()
    c = get_compte(compte_id)
    if c and c["etat"] == "bloque":
        db.execute("UPDATE comptes SET etat = 'actif', bloque = NULL WHERE id = ?",
                   (compte_id,))
        db.commit()
        audit("debloquer", _acteur(), c["email"])
        flash(f"{c['email']} a été débloqué.", "success")
    return redirect(url_for("accounts.comptes"))


@bp.route("/api/comptes/<int:compte_id>/supprimer", methods=["POST"])
@super_admin_required
def supprimer(compte_id: int):
    db = get_db()
    c = get_compte(compte_id)
    if c is None:
        return redirect(url_for("accounts.comptes"))
    # Le dernier super-admin est indestructible (spec §9.3).
    if c["role"] == "super_admin":
        flash("Impossible de supprimer un super-admin.", "error")
        return redirect(url_for("accounts.comptes"))
    db.execute("DELETE FROM comptes WHERE id = ?", (compte_id,))
    db.commit()
    audit("supprimer", _acteur(), c["email"])
    flash(f"{c['email']} a été supprimé.", "info")
    return redirect(url_for("accounts.comptes"))


# ── Impersonation « voir en tant que » (spec §6) ────────────────────────────
@bp.route("/api/comptes/<int:compte_id>/impersonate", methods=["POST"])
@super_admin_required
def impersonate(compte_id: int):
    # Pas d'impersonation en cascade, ni d'un autre super-admin (spec §6).
    if session.get("impersonator_id"):
        flash("Déjà en impersonation.", "error")
        return redirect(url_for("accounts.comptes"))
    cible = get_compte(compte_id)
    if cible is None or cible["role"] == "super_admin" or cible["etat"] != "actif":
        flash("Compte non impersonnable.", "error")
        return redirect(url_for("accounts.comptes"))

    session["impersonator_id"] = session["compte_id"]
    session["compte_id"] = compte_id
    audit("impersonate_start", _acteur(), cible["email"])
    flash(f"Tu consultes maintenant le compte de {cible['email']}.", "info")
    return redirect(url_for("main.dashboard"))


@bp.route("/api/impersonate/stop", methods=["POST"])
@login_required
def impersonate_stop():
    real_id = session.pop("impersonator_id", None)
    if real_id:
        cible = get_compte(session.get("compte_id"))
        session["compte_id"] = real_id
        audit("impersonate_stop", _acteur(), cible["email"] if cible else None)
    return redirect(url_for("main.dashboard"))
