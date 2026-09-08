"""Commandes du site (modèle en couches).

Configure les chemins (base/ + racine) puis délègue aux outils de la base :

    python manage.py setup [--preset hub|perso]   # permissions → .env
    python manage.py reset_admin ["nouveau_mdp"]   # réinitialise le mdp admin
    python manage.py set_email <email> | --clear   # rattache l'e-mail admin
    python manage.py sync_base [--ref X.Y.Z]        # met à jour la couche base/
"""

from __future__ import annotations

import os
import runpy
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "base"))
sys.path.insert(0, ROOT)

_COMMANDS = {
    "setup": "panel.setup",
    "reset_admin": "panel.reset_admin",
    "set_email": "panel.set_email",
    "sync_base": "panel.sync_base",
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        print("Commandes : " + ", ".join(_COMMANDS))
        sys.exit(1)
    module = _COMMANDS[sys.argv[1]]
    # Réaligne argv pour le module cible (comme s'il était lancé seul).
    sys.argv = [sys.argv[1]] + sys.argv[2:]
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
