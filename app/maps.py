"""Estimation du trajet (distance + durée) — gratuit, sans clé.

Chaîne robuste :
  1. **Géocodage** adresse → coordonnées :
       a) Base Adresse Nationale (api-adresse.data.gouv.fr) — France, fiable, sans
          clé ni politique d'usage stricte ;
       b) repli **Nominatim** (OpenStreetMap) pour hors-France / adresses libres.
  2. **Itinéraire** voiture → durée + distance via **OSRM** (démo publique). Si
     OSRM est indisponible (serveur de démo souvent surchargé), on retombe sur
     une **estimation approximative** à partir de la distance à vol d'oiseau.

Best-effort : ne lève jamais. `estimate()` renvoie None ou un dict. Pour un
diagnostic clair (bouton « ↻ Estimer »), `estimate_or_reason()` renvoie aussi la
raison de l'échec. Réglage `maps_enabled` (super-admin), activé par défaut.
"""

from __future__ import annotations

import logging
import math

import requests

from panel.settings import get_setting

log = logging.getLogger(__name__)

_UA = "VTC-taxi/1.0 (self-hosted; contact admin)"
_TIMEOUT = 10
_VITESSE_MOY_KMH = 45  # pour l'estimation de repli (zone mixte ville/route)


def is_enabled() -> bool:
    """Estimation activée ? (par défaut oui ; le super-admin peut la couper)."""
    return get_setting("maps_enabled") != "0"


# ─────────────────────────────────────────────────────────────────────────────
# Géocodage
# ─────────────────────────────────────────────────────────────────────────────
def _geocode_ban(adresse: str):
    """Base Adresse Nationale (France) → (lat, lon) ou None."""
    try:
        r = requests.get("https://api-adresse.data.gouv.fr/search/",
                         params={"q": adresse, "limit": 1},
                         headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        if r.status_code >= 300:
            return None
        feats = (r.json() or {}).get("features") or []
        if not feats:
            return None
        lon, lat = feats[0]["geometry"]["coordinates"]  # BAN = [lon, lat]
        return float(lat), float(lon)
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log.info("Géocodage BAN échoué (%s) : %s", adresse[:40], exc)
        return None


def _geocode_nominatim(adresse: str):
    """Nominatim (OpenStreetMap) → (lat, lon) ou None."""
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": adresse, "format": "json", "limit": 1},
                         headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        if r.status_code >= 300:
            return None
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log.info("Géocodage Nominatim échoué (%s) : %s", adresse[:40], exc)
        return None


def _geocode(adresse: str):
    adresse = (adresse or "").strip()
    if not adresse:
        return None
    return _geocode_ban(adresse) or _geocode_nominatim(adresse)


# ─────────────────────────────────────────────────────────────────────────────
# Itinéraire
# ─────────────────────────────────────────────────────────────────────────────
def _osrm(a, b):
    """OSRM démo → {distance_km, duree_min} ou None."""
    try:
        r = requests.get(
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{a[1]},{a[0]};{b[1]},{b[0]}",
            params={"overview": "false"},
            headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        if r.status_code >= 300:
            return None
        routes = (r.json() or {}).get("routes") or []
        if not routes:
            return None
        return {
            "distance_km": round(routes[0]["distance"] / 1000.0, 1),
            "duree_min": int(round(routes[0]["duration"] / 60.0)),
        }
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log.info("Itinéraire OSRM échoué : %s", exc)
        return None


def _haversine_km(a, b) -> float:
    """Distance à vol d'oiseau (km) entre deux (lat, lon)."""
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dlam = math.radians(b[1] - a[1])
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2)
    return r * 2 * math.asin(math.sqrt(h))


# ─────────────────────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────────────────────
def estimate_or_reason(depart: str, arrivee: str):
    """Renvoie (résultat|None, raison). `résultat` = {distance_km, duree_min, approx}."""
    if not is_enabled():
        return None, "L'estimation est désactivée (Paramètres → Estimation de trajet)."
    depart = (depart or "").strip()
    arrivee = (arrivee or "").strip()
    if not depart or not arrivee:
        return None, "Il faut une adresse de départ ET une adresse d'arrivée."
    a = _geocode(depart)
    if not a:
        return None, (f"Adresse de départ introuvable : « {depart} ». "
                      "Précise-la (numéro, ville, code postal).")
    b = _geocode(arrivee)
    if not b:
        return None, (f"Adresse d'arrivée introuvable : « {arrivee} ». "
                      "Précise-la (numéro, ville, code postal).")
    route = _osrm(a, b)
    if route:
        route["approx"] = False
        return route, ""
    # Repli : distance à vol d'oiseau × 1.3 (détour routier), vitesse moyenne.
    km = round(_haversine_km(a, b) * 1.3, 1)
    duree = max(1, int(round(km / _VITESSE_MOY_KMH * 60)))
    return ({"distance_km": km, "duree_min": duree, "approx": True},
            "Itinéraire routier indisponible : estimation approximative (à vol d'oiseau).")


def estimate(depart: str, arrivee: str) -> dict | None:
    """Best-effort : {distance_km, duree_min, approx} ou None (jamais d'exception)."""
    res, _ = estimate_or_reason(depart, arrivee)
    return res


def fmt_duree(minutes: int | None) -> str:
    """Formate une durée en minutes : « 1 h 05 » / « 25 min »."""
    if not minutes:
        return ""
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"
