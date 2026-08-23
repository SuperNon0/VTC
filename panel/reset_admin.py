"""Réinitialise le mot de passe du super-admin local (accès LAN).

Utile si tu as oublié le mot de passe : cette commande s'exécute sur le serveur
(accès shell), donc elle ne dépend pas d'être connecté au site.

Usage :
    python -m panel.reset_admin                 # demande le nouveau mdp (masqué)
    python -m panel.reset_admin "NouveauMdp!"   # non interactif (ex. scripts)

Sur un déploiement LXC : voir deploy/reset_admin.sh.
"""

from __future__ import annotations

import getpass
import sys
import time

from werkzeug.security import generate_password_hash

from . import create_app
from .db import audit, get_db

MIN_LEN = 8


def _lire_mdp() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    mdp = getpass.getpass("Nouveau mot de passe super-admin : ")
    if mdp != getpass.getpass("Confirme : "):
        print("✗ Les mots de passe ne correspondent pas.")
        sys.exit(1)
    return mdp


def main() -> None:
    mdp = _lire_mdp()
    if len(mdp) < MIN_LEN:
        print(f"✗ Mot de passe trop court (minimum {MIN_LEN} caractères).")
        sys.exit(1)

    app = create_app()
    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT id, email FROM comptes WHERE role = 'super_admin' "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        h = generate_password_hash(mdp)
        now = int(time.time())
        if row is None:
            # Aucun super-admin : on en crée un (login local seul).
            db.execute(
                "INSERT INTO comptes (email, role, etat, mdp_hash, cree, valide) "
                "VALUES (NULL, 'super_admin', 'actif', ?, ?, ?)",
                (h, now, now),
            )
            cible = "super-admin (nouveau)"
        else:
            db.execute(
                "UPDATE comptes SET mdp_hash = ?, etat = 'actif' WHERE id = ?",
                (h, row["id"]),
            )
            cible = row["email"] or "super-admin local"
        db.commit()
        audit("reset_mdp_cli", acteur="cli", cible=cible)

    print(f"✓ Mot de passe du {cible} réinitialisé.")


if __name__ == "__main__":
    main()
