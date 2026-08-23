"""Contenu métier : le hub (catégories → sections → apps / raccourcis).

Bibliothèque **partagée** (décision projet, cf. authentification-v2.md §7) :
une seule configuration commune à tous les comptes, stockée en base dans la
table `hub` (une ligne JSON). Éditable par le super-admin uniquement.
"""

from __future__ import annotations

import json

from .db import get_db

# Configuration de départ (au premier lancement). Reprend les outils existants.
DEFAULT_HUB = {
    "settings": {
        "weather": {"lat": 43.5378, "lon": 4.1347, "label": "Le Grau-du-Roi"},
    },
    "categories": [
        {
            "id": "infra",
            "name": "Infrastructure",
            "sections": [
                {"id": "serveurs", "name": "Serveurs", "items": [
                    {"id": "proxmox", "type": "app", "icon": {"kind": "emoji", "value": "📺"},
                     "title": "Proxmox", "desc": "Panneaux de configuration",
                     "url": "https://proxmox.super-nono.cc", "color": "#b56912"},
                ]},
                {"id": "automatisation", "name": "Automatisation", "items": [
                    {"id": "n8n", "type": "app", "icon": {"kind": "emoji", "value": "🔗"},
                     "title": "n8n", "desc": "Gestionnaire d'automatisation",
                     "url": "https://nnn.super-nono.cc", "color": "#6e0202"},
                    {"id": "botpanel", "type": "app", "icon": {"kind": "emoji", "value": "☎️"},
                     "title": "BotPanel", "desc": "Notifications & actions Discord",
                     "url": "https://botpanel.super-nono.cc", "color": "#151ed4"},
                    {"id": "discopanel", "type": "app", "icon": {"kind": "emoji", "value": "🔧"},
                     "title": "DiscoPanel", "desc": "Gestion serveur Minecraft",
                     "url": "https://mc.super-nono.cc", "color": "#2e703b"},
                ]},
            ],
        },
        {
            "id": "perso",
            "name": "Perso",
            "sections": [
                {"id": "mes-apps", "name": "Mes applications", "items": [
                    {"id": "fuellog", "type": "app", "icon": {"kind": "emoji", "value": "⛽"},
                     "title": "FuelLog", "desc": "Suivi carburant · stations",
                     "url": "https://fuel.super-nono.cc", "color": "#e43737"},
                    {"id": "salaire", "type": "app", "icon": {"kind": "emoji", "value": "💶"},
                     "title": "Salaire", "desc": "Calculateur · fiches de paie",
                     "url": "https://salaire.super-nono.cc", "color": "#47e31b"},
                    {"id": "recipe", "type": "app", "icon": {"kind": "emoji", "value": "📝"},
                     "title": "RecipeLogs", "desc": "Gestionnaire de recettes",
                     "url": "https://recipe.super-nono.cc", "color": "#a78cfa"},
                ]},
            ],
        },
        {
            "id": "outils",
            "name": "Outils",
            "sections": [
                {"id": "utilitaires", "name": "Utilitaires", "items": [
                    {"id": "pdf", "type": "app", "icon": {"kind": "emoji", "value": "📄"},
                     "title": "BentoPDF", "desc": "Outils PDF",
                     "url": "https://pdf.super-nono.cc", "color": "#5fa5fa"},
                    {"id": "multioutils", "type": "app", "icon": {"kind": "emoji", "value": "🛠️"},
                     "title": "MultiOutils", "desc": "Capture & presse-papier",
                     "url": "https://multioutils.super-nono.cc", "color": "#4bc40f"},
                ]},
            ],
        },
    ],
}


def get_hub() -> dict:
    """Retourne la configuration du hub (amorcée au défaut si absente)."""
    row = get_db().execute("SELECT data FROM hub WHERE id = 1").fetchone()
    if row is None:
        save_hub(DEFAULT_HUB)
        return json.loads(json.dumps(DEFAULT_HUB))
    return json.loads(row["data"])


def save_hub(cfg: dict) -> None:
    """Enregistre la configuration complète du hub (une ligne partagée)."""
    db = get_db()
    db.execute(
        "INSERT INTO hub (id, data) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
        (json.dumps(cfg, ensure_ascii=False),),
    )
    db.commit()
