"""Surcouche projet — EXEMPLE.

Copie ce dossier `app.example/` en `app/` pour démarrer ton projet. Dès qu'un
dossier `app/` existe, la base le charge automatiquement (voir base/panel/__init__.py) :
  - `register(flask_app)` ci-dessous branche tes écrans (blueprints) ;
  - `app/templates/` s'ajoute (et prime) sur les templates de la base ;
  - `app/schema.sql` (optionnel) crée tes tables métier.

⚠️ Ne modifie JAMAIS le dossier `base/` : la base se met à jour toute seule
(bouton « Mettre à jour la base »). Tout ton code vit ici, dans `app/`.
"""

from __future__ import annotations


def register(flask_app) -> None:
    """Point d'entrée appelé par la base pour brancher la surcouche."""
    from .routes import bp
    flask_app.register_blueprint(bp)

    # Réglages de l'application : on déclare un partial que la base inclura dans
    # sa page /reglages (même thème, même cadre). Retire cette ligne si ton
    # application n'a aucun réglage. Le partial vit dans app/templates/.
    flask_app.config["APP_REGLAGES_TEMPLATE"] = "app_reglages.html"
