"""Point d'entrée de développement (modèle en couches).

Assemble la couche « base » (dossier base/, verrouillé) et la surcouche projet
(dossier app/, tes écrans). Voir base/docs/… et le README.

    python run.py            # http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "base"))  # → import panel (la base)
sys.path.insert(0, ROOT)                          # → import app (ta surcouche)

from panel import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )
