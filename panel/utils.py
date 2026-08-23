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
# Export vers le calendrier natif (cahier §6.6)
# ─────────────────────────────────────────────────────────────────────────────
def _utc_stamp(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def course_titre(course) -> str:
    nom = (course["client_nom"] or "Client").strip()
    return f"Course taxi — {nom}"


def course_description(course) -> str:
    lignes = []
    if course["client_nom"]:
        lignes.append(f"Client : {course['client_nom']}")
    if course["client_tel"]:
        lignes.append(f"Téléphone : {course['client_tel']}")
    if course["depart"]:
        lignes.append(f"Prise en charge : {course['depart']}")
    if course["arrivee"]:
        lignes.append(f"Dépose : {course['arrivee']}")
    if course["prix"] is not None:
        lignes.append(f"Prix : {course['prix']:.2f} €")
    if course["notes"]:
        lignes.append(f"Notes : {course['notes']}")
    return "\n".join(lignes)


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
