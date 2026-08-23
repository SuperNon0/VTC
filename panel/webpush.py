"""Web Push (PWA) — notifications de nouvelle course assignée (cahier §6.5 / §7).

Indépendant de BotPanel (cahier §8) : les notifications métier des conducteurs
passent uniquement par Web Push, avec des clés VAPID générées côté serveur.

Fonctionnement :
  - Les clés VAPID sont générées **une seule fois** et stockées en base
    (`app_settings`). La clé publique est exposée au navigateur (§ /api/push/key)
    pour l'abonnement ; la clé privée signe les envois.
  - Chaque appareil enregistre une souscription (`push_subscriptions`).
  - `notifier_conducteur()` envoie à toutes les souscriptions du conducteur
    assigné. Les souscriptions expirées (HTTP 404/410) sont purgées.

Dégradé propre : si `pywebpush`/`cryptography` sont absents, les envois sont
ignorés sans casser la création de course (le calendrier reste la source
fiable, cahier §6.5).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time

from flask import current_app

from .db import get_db
from .settings import get_setting, set_setting

log = logging.getLogger(__name__)

try:
    from pywebpush import WebPushException, webpush
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    _AVAILABLE = True
except Exception:  # pragma: no cover - dépendances optionnelles
    _AVAILABLE = False


def is_available() -> bool:
    return _AVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# Clés VAPID
# ─────────────────────────────────────────────────────────────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def ensure_vapid_keys() -> dict | None:
    """Génère (une fois) et renvoie les clés VAPID ; None si indisponible."""
    if not _AVAILABLE:
        return None
    priv_pem = get_setting("vapid_private_pem")
    pub_b64 = get_setting("vapid_public_b64")
    if priv_pem and pub_b64:
        return {"private_pem": priv_pem, "public_b64": pub_b64}

    key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    raw_pub = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64 = _b64url(raw_pub)
    set_setting("vapid_private_pem", priv_pem)
    set_setting("vapid_public_b64", pub_b64)
    log.info("Clés VAPID générées.")
    return {"private_pem": priv_pem, "public_b64": pub_b64}


def public_key() -> str | None:
    keys = ensure_vapid_keys()
    return keys["public_b64"] if keys else None


def _private_key_path() -> str:
    """Écrit la clé privée VAPID dans un fichier (py_vapid lit un PEM sur disque)."""
    keys = ensure_vapid_keys()
    if not keys:
        raise RuntimeError("VAPID indisponible")
    path = os.path.join(
        os.path.dirname(current_app.config["DATABASE_PATH"]), "vapid_private.pem"
    )
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="ascii") as fh:
            fh.write(keys["private_pem"])
        os.chmod(path, 0o600)
    return path


def _vapid_sub() -> str:
    email = (current_app.config.get("SUPERADMIN_EMAIL") or "").strip()
    return f"mailto:{email}" if email else "mailto:admin@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# Souscriptions
# ─────────────────────────────────────────────────────────────────────────────
def enregistrer_souscription(compte_id: int, sub: dict, ua: str | None) -> bool:
    """Enregistre/rafraîchit la souscription d'un appareil pour un compte."""
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not endpoint or not p256dh or not auth:
        return False
    db = get_db()
    db.execute(
        """INSERT INTO push_subscriptions (compte_id, endpoint, p256dh, auth, ua, cree)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(endpoint) DO UPDATE SET
             compte_id = excluded.compte_id, p256dh = excluded.p256dh,
             auth = excluded.auth, ua = excluded.ua""",
        (compte_id, endpoint, p256dh, auth, ua, int(time.time())),
    )
    db.commit()
    return True


def supprimer_souscription(endpoint: str) -> None:
    db = get_db()
    db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
    db.commit()


def compte_a_des_souscriptions(compte_id: int) -> bool:
    row = get_db().execute(
        "SELECT 1 FROM push_subscriptions WHERE compte_id = ? LIMIT 1", (compte_id,)
    ).fetchone()
    return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# Envoi
# ─────────────────────────────────────────────────────────────────────────────
def notifier_conducteur(compte_id: int, titre: str, corps: str,
                        url: str = "/") -> int:
    """Envoie une notification push à tous les appareils d'un conducteur.

    Ne lève jamais : renvoie le nombre d'envois réussis. Purge les
    souscriptions périmées.
    """
    if not _AVAILABLE:
        log.debug("Web Push indisponible — notification ignorée.")
        return 0
    keys = ensure_vapid_keys()
    if not keys:
        return 0

    db = get_db()
    subs = db.execute(
        "SELECT * FROM push_subscriptions WHERE compte_id = ?", (compte_id,)
    ).fetchall()
    if not subs:
        return 0

    payload = json.dumps({"title": titre, "body": corps, "url": url},
                         ensure_ascii=False)
    try:
        pk_path = _private_key_path()
    except Exception as exc:
        log.warning("Clé VAPID indisponible : %s", exc)
        return 0

    envoyes = 0
    for s in subs:
        info = {"endpoint": s["endpoint"],
                "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=pk_path,
                vapid_claims={"sub": _vapid_sub()},
                ttl=3600,
            )
            envoyes += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                supprimer_souscription(s["endpoint"])
                log.info("Souscription périmée purgée (%s).", status)
            else:
                log.warning("Échec Web Push : %s", exc)
        except Exception as exc:  # réseau, encodage…
            log.warning("Échec Web Push (autre) : %s", exc)
    return envoyes
