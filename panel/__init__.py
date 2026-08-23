"""Site de base — application factory Flask.

Assemble la config, la base SQLite, l'authentification (Cloudflare Zero Trust +
login local), la gestion des comptes et l'intégration des notifications BotPanel.
"""

from __future__ import annotations

from flask import Flask, g, request, session

from .config import Config


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    from . import db as db_module
    app.teardown_appcontext(db_module.close_db)

    # Schéma + amorce du super-admin au démarrage.
    with app.app_context():
        db_module.init_db()

    # --- Blueprints ---
    from .routes.auth_routes import bp as auth_bp
    from .routes.accounts_routes import bp as accounts_bp
    from .routes.main import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(main_bp)

    # --- Contexte de template partagé (marque + bandeau impersonation) ---
    @app.context_processor
    def inject_globals():
        from .auth import get_compte
        impersonation = None
        if session.get("impersonator_id"):
            cible = get_compte(session.get("compte_id"))
            if cible is not None:
                impersonation = {"email": cible["email"]}
        return {
            "brand": {
                "prefix": app.config["BRAND_PREFIX"],
                "suffix": app.config["BRAND_SUFFIX"],
                "badge": app.config["BRAND_BADGE"],
            },
            "impersonation": impersonation,
        }

    # --- Toutes les routes /api/* en no-store (spec §8) ---
    @app.after_request
    def no_store_api(resp):
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app
