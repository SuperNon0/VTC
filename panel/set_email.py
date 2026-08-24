"""Rattache un e-mail Google au super-admin — et unifie les comptes en un seul.

But : obtenir UN SEUL compte super-admin qui réunit le login local (mot de
passe) ET l'e-mail Google (Cloudflare), sans manipulation dans l'interface.

Cette commande, exécutée sur le serveur (accès shell) :
  1. choisit le super-admin principal (celui qui a un mot de passe local, sinon
     le plus ancien) ;
  2. fusionne dans ce compte tout AUTRE super-admin (doublon d'amorçage) et le
     compte qui détient déjà l'e-mail visé — leurs courses et abonnements push
     sont réattribués, puis ces comptes sont supprimés ;
  3. rattache l'e-mail au super-admin principal.

Usage :
    python -m panel.set_email ton.email@gmail.com     # rattache l'e-mail
    python -m panel.set_email --clear                 # détache l'e-mail

Sur un déploiement LXC : voir deploy/set_email.sh.
"""

from __future__ import annotations

import sys
import time

from . import create_app
from .db import audit, get_db


def _merge_into(db, source_id: int, target_id: int) -> None:
    """Réattribue les données du compte `source` au compte `target`, puis supprime source."""
    if source_id == target_id:
        return
    db.execute("UPDATE courses SET createur_id = ? WHERE createur_id = ?",
               (target_id, source_id))
    db.execute("UPDATE courses SET conducteur_id = ? WHERE conducteur_id = ?",
               (target_id, source_id))
    db.execute("UPDATE push_subscriptions SET compte_id = ? WHERE compte_id = ?",
               (target_id, source_id))
    db.execute("DELETE FROM comptes WHERE id = ?", (source_id,))


def main() -> None:
    args = sys.argv[1:]
    clear = "--clear" in args
    email = None
    if not clear:
        rest = [a for a in args if not a.startswith("-")]
        if not rest:
            print("Usage : python -m panel.set_email ton.email@gmail.com  (ou --clear)")
            sys.exit(1)
        email = rest[0].strip().lower()
        if "@" not in email:
            print(f"✗ « {email} » ne ressemble pas à un e-mail.")
            sys.exit(1)

    app = create_app()
    with app.app_context():
        db = get_db()
        supers = db.execute(
            "SELECT id, email, mdp_hash FROM comptes WHERE role = 'super_admin' "
            "ORDER BY (mdp_hash IS NOT NULL) DESC, id"
        ).fetchall()
        if not supers:
            print("✗ Aucun super-admin. Lance d'abord : python -m panel.reset_admin")
            sys.exit(1)

        target = supers[0]["id"]

        # 1) Fusionne les super-admins en double dans le principal.
        for row in supers[1:]:
            _merge_into(db, row["id"], target)
            print(f"→ Super-admin en double (id {row['id']}) fusionné.")

        if clear:
            db.execute("UPDATE comptes SET email = NULL WHERE id = ?", (target,))
            db.commit()
            audit("set_email_cli", acteur="cli", cible="(détaché)")
            print("✓ E-mail détaché : connexion par mot de passe uniquement.")
            return

        # 2) Fusionne le compte qui détient déjà cet e-mail (ex. compte membre).
        autre = db.execute(
            "SELECT id FROM comptes WHERE email = ? AND id != ?", (email, target)
        ).fetchone()
        if autre is not None:
            _merge_into(db, autre["id"], target)
            print(f"→ Compte « {email} » (id {autre['id']}) fusionné dans le super-admin.")

        # 3) Rattache l'e-mail au super-admin principal.
        db.execute("UPDATE comptes SET email = ?, etat = 'actif' WHERE id = ?",
                   (email, target))
        db.commit()
        audit("set_email_cli", acteur="cli", cible=email)

    print(f"✓ E-mail {email} rattaché au super-admin.")
    print("  Tu peux maintenant te connecter par mot de passe OU via Cloudflare "
          "avec cet e-mail — c'est le même compte.")


if __name__ == "__main__":
    main()
