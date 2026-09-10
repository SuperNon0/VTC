"""Surcouche métier VTC (taxi/VTC) — se branche sur la base verrouillée.

La base (`base/panel/`) détecte ce dossier `app/` et l'assemble automatiquement :
  - `register(flask_app)` ci-dessous enregistre les écrans métier (blueprints
    `main` + `config`, dont l'accueil `/`) ;
  - `app/templates/` s'ajoute et prime sur les templates de la base ;
  - `app/schema.sql` crée les tables métier (courses, clients, tarifs, lieux…).

⚠️ Ne modifie JAMAIS le dossier `base/` : la base se met à jour toute seule
(Paramètres → « Mettre à jour la base »). Tout le métier vit ici, dans `app/`.
"""

from __future__ import annotations


def register(flask_app) -> None:
    """Point d'entrée appelé par la base pour brancher la surcouche métier."""
    from .routes import config_bp, main_bp
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(config_bp)

    # La page /reglages de la base inclut ce partial (menu des réglages métier :
    # IA, tarifs, lieux, calendrier, notifications, estimation). Même thème,
    # même cadre — voir base/panel/routes/accounts_routes.py::reglages.
    flask_app.config["APP_REGLAGES_TEMPLATE"] = "app_reglages.html"

    # Version des ressources statiques (app.css…) : dérivée de la date de
    # modification du CSS. Ajoutée en `?v=` sur le <link> (voir _layout.html) pour
    # forcer le rechargement après une mise à jour — iOS met en cache les
    # ressources de l'app ajoutée à l'écran d'accueil de façon très agressive.
    import os
    _css = os.path.join(os.path.dirname(__file__), "static", "app.css")
    try:
        _asset_version = str(int(os.path.getmtime(_css)))
    except OSError:
        _asset_version = "0"

    @flask_app.context_processor
    def _inject_asset_version():
        return {"asset_version": _asset_version}

    # La couche « base » suit la branche `main` du site-base : « Mettre à jour la
    # base » (sync_base) récupère les correctifs sans qu'un tag soit publié.
    # sync_base lit ce réglage via current_app.config (point d'extension prévu par
    # la base). Un BASE_REPO_REF déjà présent dans le .env reste prioritaire.
    if not flask_app.config.get("BASE_REPO_REF"):
        flask_app.config["BASE_REPO_REF"] = "main"

    # Migration idempotente des colonnes métier ajoutées après coup (ex. lieux.ville_id)
    # sur une base déjà créée. register() est appelé hors contexte → on en ouvre un.
    from . import courses as _courses
    with flask_app.app_context():
        _courses.ensure_schema()
