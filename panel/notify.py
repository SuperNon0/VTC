"""Intégration BotPanel — https://github.com/SuperNon0/botpanel

Le site n'a RIEN à savoir de Discord : il déclenche une notification par son
*slug* (créé une fois dans BotPanel), et peut injecter des variables dynamiques
qui remplissent les `{var:nom}` du template côté panel.

    POST {BOTPANEL_URL}/api/notify
    { "id": "<slug>", "vars": { "nom": "valeur", ... } }

Voir docs/notifications-botpanel.md.
"""

from __future__ import annotations

import logging

import requests
from flask import current_app

log = logging.getLogger(__name__)


def notify(slug: str, **variables: object) -> bool:
    """Déclenche la notification `slug` sur BotPanel.

    Les `variables` fournies remplissent les `{var:nom}` du template BotPanel.
    Ne lève JAMAIS : une notification qui échoue ne doit pas casser une requête
    métier. Renvoie True si BotPanel a répondu 2xx.

    Exemples :
        notify("acces_demande", email="jean@gmail.com")
        notify("backup_done", vmid="100", duree="2m34s", taille="2.1 Go")
    """
    base_url = (current_app.config.get("BOTPANEL_URL") or "").rstrip("/")
    if not base_url:
        log.debug("BotPanel non configuré (BOTPANEL_URL vide) — notify(%s) ignoré", slug)
        return False

    payload: dict[str, object] = {"id": slug}
    if variables:
        payload["vars"] = {k: str(v) for k, v in variables.items()}

    try:
        resp = requests.post(
            f"{base_url}/api/notify",
            json=payload,
            timeout=current_app.config.get("BOTPANEL_TIMEOUT", 5),
        )
        if resp.status_code >= 300:
            log.warning("BotPanel notify(%s) → HTTP %s : %s", slug, resp.status_code, resp.text[:200])
            return False
        return True
    except requests.RequestException as exc:  # réseau, timeout, DNS…
        log.warning("BotPanel notify(%s) injoignable : %s", slug, exc)
        return False
