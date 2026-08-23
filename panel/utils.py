"""Petits utilitaires partagés."""

from __future__ import annotations

from datetime import datetime

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
