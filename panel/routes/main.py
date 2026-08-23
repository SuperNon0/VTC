"""Le hub (contenu métier) : dashboard + API d'édition (super-admin).

Bibliothèque partagée : une configuration commune éditable par le super-admin.
Consultable par tout compte actif.
"""

from __future__ import annotations

import os
import time

from flask import (Blueprint, current_app, jsonify, render_template, request,
                   send_from_directory)

from ..auth import current_compte, is_super_admin, login_required
from ..db import audit
from ..hub import get_hub, save_hub

bp = Blueprint("main", __name__)


def _uploads_dir() -> str:
    d = os.path.join(os.path.dirname(current_app.config["DATABASE_PATH"]), "uploads")
    os.makedirs(d, exist_ok=True)
    return d


def _require_super_admin_json():
    """Garde JSON pour les routes /api/* (401/403 au lieu d'une redirection)."""
    c = current_compte()
    if c is None or c["etat"] != "actif":
        return jsonify(ok=False, error="non authentifié"), 401
    if not is_super_admin():
        return jsonify(ok=False, error="réservé au super-admin"), 403
    return None


# ─── Dashboard ────────────────────────────────────────────────────────────────
@bp.route("/")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        compte=current_compte(),
        is_super_admin=is_super_admin(),
    )


# ─── API du hub ───────────────────────────────────────────────────────────────
@bp.get("/api/hub")
@login_required
def api_hub_get():
    return jsonify(get_hub())


@bp.put("/api/hub")
def api_hub_put():
    guard = _require_super_admin_json()
    if guard:
        return guard
    cfg = request.get_json(silent=True)
    if not cfg or not isinstance(cfg.get("categories"), list):
        return jsonify(ok=False, error="config invalide"), 400
    save_hub(cfg)
    return jsonify(ok=True)


@bp.post("/api/hub/upload")
def api_hub_upload():
    guard = _require_super_admin_json()
    if guard:
        return guard
    f = request.files.get("file")
    if not f or not (f.mimetype or "").startswith("image/"):
        return jsonify(ok=False, error="image requise"), 400
    ext = os.path.splitext(f.filename or "")[1].lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}:
        ext = ".png"
    name = f"{int(time.time() * 1000):x}{ext}"
    f.save(os.path.join(_uploads_dir(), name))
    return jsonify(ok=True, url="/uploads/" + name)


@bp.get("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(_uploads_dir(), filename)
