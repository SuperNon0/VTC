"""Estimation du trajet (distance + durée) via OpenStreetMap — gratuit, sans clé.

Deux services publics :
  - **Nominatim** (geocodage adresse → coordonnées)
  - **OSRM** (itinéraire voiture → durée + distance)

Best-effort : ne lève jamais. Si Internet est injoignable, si une adresse n'est
pas géocodée, ou si l'estimation est désactivée, renvoie None — la création de
course n'est jamais bloquée (le calendrier reste la source fiable).

Réglage : `maps_enabled` dans `app_settings` (super-admin), activé par défaut.
Respecte la politique d'usage Nominatim (User-Agent explicite, faible volume).
"""

from __future__ import annotations

import logging

import requests

from .settings import get_setting

log = logging.getLogger(__name__)

_UA = "VTC-taxi/1.0 (self-hosted)"
_TIMEOUT = 8


def is_enabled() -> bool:
    """Estimation activée ? (par défaut oui ; le super-admin peut la couper)."""
    val = get_setting("maps_enabled")
    return val != "0"


def _geocode(adresse: str) -> tuple[float, float] | None:
    adresse = (adresse or "").strip()
    if not adresse:
        return None
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": adresse, "format": "json", "limit": 1},
            headers={"User-Agent": _UA},
            timeout=_TIMEOUT,
        )
        if r.status_code >= 300:
            return None
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log.info("Géocodage échoué (%s) : %s", adresse[:40], exc)
        return None


def estimate(depart: str, arrivee: str) -> dict | None:
    """Estime {distance_km, duree_min} entre deux adresses. None si indisponible."""
    if not is_enabled():
        return None
    a = _geocode(depart)
    b = _geocode(arrivee)
    if not a or not b:
        return None
    try:
        r = requests.get(
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{a[1]},{a[0]};{b[1]},{b[0]}",
            params={"overview": "false"},
            headers={"User-Agent": _UA},
            timeout=_TIMEOUT,
        )
        if r.status_code >= 300:
            return None
        routes = r.json().get("routes") or []
        if not routes:
            return None
        dur_s = routes[0]["duration"]
        dist_m = routes[0]["distance"]
        return {
            "distance_km": round(dist_m / 1000.0, 1),
            "duree_min": int(round(dur_s / 60.0)),
        }
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log.info("Itinéraire OSRM échoué : %s", exc)
        return None


def fmt_duree(minutes: int | None) -> str:
    """Formate une durée en minutes : « 1 h 05 » / « 25 min »."""
    if not minutes:
        return ""
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"
