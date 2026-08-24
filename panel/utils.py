"""Petits utilitaires partagés."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre"]


def fmt_dt(ts: int | None, with_time: bool = True) -> str:
    """Formate un timestamp Unix en français : « 12 août 2026 à 14 h 30 »."""
    if not ts:
        return ""
    d = datetime.fromtimestamp(ts)
    s = f"{d.day} {_MOIS[d.month - 1]} {d.year}"
    if with_time:
        s += f" à {d.hour} h {d.minute:02d}"
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Export vers le calendrier natif (cahier §6.6) — modèles personnalisables
#
# Le titre et les notes de l'événement calendrier sont construits à partir de
# deux modèles texte contenant des **placeholders** entre crochets, ex :
# « Prix : [prix] ». Ces modèles sont modifiables dans les Paramètres
# (super-admin uniquement) ; à défaut, les valeurs par défaut ci-dessous
# s'appliquent.
# ─────────────────────────────────────────────────────────────────────────────

# Placeholders disponibles → description affichée dans l'aide des Paramètres.
CAL_PLACEHOLDERS = {
    "nom": "Nom du client",
    "telephone": "Numéro de téléphone",
    "depart": "Lieu de prise en charge",
    "arrivee": "Lieu de dépose",
    "prix": "Prix (ex : 15.00 €)",
    "date": "Date et heure",
    "duree": "Durée de trajet estimée (ex : 25 min)",
    "statut": "Statut de la course",
    "habitue": "« Habitué » ou « Nouveau client »",
    "notes": "Notes libres de la course",
}

# Modèle par défaut du TITRE de l'événement (ce qui s'affiche en gros).
DEFAULT_CAL_TITLE = "[nom] · [depart] → [arrivee]"

# Modèle par défaut des NOTES de l'événement (toutes les infos).
DEFAULT_CAL_NOTES = (
    "Client : [nom] ([habitue])\n"
    "Téléphone : [telephone]\n"
    "Départ : [depart]\n"
    "Arrivée : [arrivee]\n"
    "Prix : [prix]\n"
    "Date : [date]\n"
    "Trajet estimé : [duree]\n"
    "Notes : [notes]"
)


def _utc_stamp(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# Notifications Web Push — titre + corps personnalisables (mêmes placeholders)
# ─────────────────────────────────────────────────────────────────────────────
NOTIF_PLACEHOLDERS = {
    "nom": "Nom du client",
    "telephone": "Téléphone",
    "depart": "Lieu de prise en charge",
    "arrivee": "Lieu de dépose",
    "prix": "Prix",
    "date": "Date et heure",
    "duree": "Durée de trajet estimée",
}
DEFAULT_NOTIF_TITLE = "Nouvelle course assignée"
DEFAULT_NOTIF_BODY = "[date] · [depart] → [arrivee]"


def _course_get(c, key):
    """Accès tolérant à une clé, que `c` soit un dict ou une Row SQLite."""
    try:
        return c[key]
    except (KeyError, IndexError, TypeError):
        return None


def label_compte(c) -> str:
    """Nom lisible d'un compte : nom d'affichage, sinon e-mail, sinon repli.

    Utilisé partout où un conducteur est présenté (au lieu de son e-mail brut).
    """
    nom = (_course_get(c, "nom") or "").strip()
    if nom:
        return nom
    email = (_course_get(c, "email") or "").strip()
    if email:
        return email
    return ("Super-admin (accès local)"
            if _course_get(c, "role") == "super_admin" else "Compte sans nom")


def _notif_values(c) -> dict:
    from .maps import fmt_duree
    prix = _course_get(c, "prix")
    return {
        "nom": (_course_get(c, "client_nom") or "").strip() or "client",
        "telephone": (_course_get(c, "client_tel") or "").strip(),
        "depart": (_course_get(c, "depart") or "").strip(),
        "arrivee": (_course_get(c, "arrivee") or "").strip(),
        "prix": f"{prix:.2f} €" if prix is not None else "",
        "date": fmt_dt(_course_get(c, "quand")),
        "duree": fmt_duree(_course_get(c, "duree_min")),
    }


def notif_title_template() -> str:
    from .settings import get_setting
    return get_setting("push_title_template") or DEFAULT_NOTIF_TITLE


def notif_body_template() -> str:
    from .settings import get_setting
    return get_setting("push_body_template") or DEFAULT_NOTIF_BODY


def notif_titre(course) -> str:
    t = _render_template(notif_title_template(), _notif_values(course)).strip()
    return t or DEFAULT_NOTIF_TITLE


def notif_corps(course) -> str:
    return _render_template(notif_body_template(), _notif_values(course)).strip()


def _cal_values(course) -> dict:
    """Valeurs concrètes des placeholders pour une course donnée."""
    from .courses import STATUT_LABELS  # import tardif : évite tout couplage
    from .maps import fmt_duree
    prix = f"{course['prix']:.2f} €" if course["prix"] is not None else ""
    return {
        "nom": (course["client_nom"] or "").strip(),
        "telephone": (course["client_tel"] or "").strip(),
        "depart": (course["depart"] or "").strip(),
        "arrivee": (course["arrivee"] or "").strip(),
        "prix": prix,
        "date": fmt_dt(course["quand"]),
        "duree": fmt_duree(course["duree_min"]),
        "statut": STATUT_LABELS.get(course["statut"], course["statut"] or ""),
        "habitue": "Habitué" if course["client_id"] else "Nouveau client",
        "notes": (course["notes"] or "").strip(),
    }


def _render_template(tpl: str, values: dict) -> str:
    """Remplace chaque [placeholder] par sa valeur (chaîne vide si inconnue)."""
    out = tpl or ""
    for key, val in values.items():
        out = out.replace(f"[{key}]", val)
    return out


def cal_title_template() -> str:
    from .settings import get_setting
    t = get_setting("cal_title_template")
    return t if t else DEFAULT_CAL_TITLE


def cal_notes_template() -> str:
    from .settings import get_setting
    t = get_setting("cal_notes_template")
    return t if t else DEFAULT_CAL_NOTES


def course_titre(course) -> str:
    titre = _render_template(cal_title_template(), _cal_values(course)).strip()
    return titre or "Course taxi"


def course_description(course) -> str:
    return _render_template(cal_notes_template(), _cal_values(course)).strip()


def google_calendar_url(course, duree_min: int = 60) -> str:
    """Lien Google Agenda pré-rempli (Android, cahier §6.6)."""
    start = int(course["quand"] or 0)
    end = start + duree_min * 60
    params = {
        "action": "TEMPLATE",
        "text": course_titre(course),
        "dates": f"{_utc_stamp(start)}/{_utc_stamp(end)}",
        "details": course_description(course),
        "location": course["depart"] or "",
    }
    query = "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
    return "https://calendar.google.com/calendar/render?" + query


def _ics_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;") \
        .replace(",", "\\,").replace("\n", "\\n")


def course_ics(course, duree_min: int = 60) -> str:
    """Génère un fichier .ics téléchargeable (iPhone, cahier §6.6)."""
    start = int(course["quand"] or 0)
    end = start + duree_min * 60
    now = _utc_stamp(int(datetime.now(tz=timezone.utc).timestamp()))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VTC//Course//FR",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:course-{course['id']}@vtc",
        f"DTSTAMP:{now}",
        f"DTSTART:{_utc_stamp(start)}",
        f"DTEND:{_utc_stamp(end)}",
        f"SUMMARY:{_ics_escape(course_titre(course))}",
        f"DESCRIPTION:{_ics_escape(course_description(course))}",
        f"LOCATION:{_ics_escape(course['depart'] or '')}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
