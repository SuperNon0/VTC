#!/usr/bin/env bash
#
# VTC — diagnostiquer l'estimation de trajet (géocodage + itinéraire).
# Montre si le serveur joint bien les services externes, puis fait un vrai test.
#
#   sudo bash /opt/site-base/deploy/check_estimation.sh
#
set -uo pipefail

INSTALL_DIR="/opt/site-base"
PY="${INSTALL_DIR}/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "──────────── Connectivité vers les services (curl) ────────────"
declare -A URLS=(
  ["Adresse (BAN, géocodage FR)"]="https://api-adresse.data.gouv.fr/search/?q=Gare+du+Grau-du-Roi&limit=1"
  ["Nominatim (géocodage repli)"]="https://nominatim.openstreetmap.org/search?q=Aigues-Mortes&format=json&limit=1"
  ["OSRM (itinéraire voiture)"]="https://router.project-osrm.org/route/v1/driving/4.134,43.537;4.192,43.566?overview=false"
)
for nom in "${!URLS[@]}"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -A "VTC-taxi/1.0" --max-time 12 "${URLS[$nom]}" 2>/dev/null || echo "ERR")
  if [ "$code" = "200" ]; then etat="OK ✓"; else etat="ÉCHEC ($code)"; fi
  printf "  %-32s %s\n" "$nom" "$etat"
done

echo
echo "──────────── Test réel de l'estimation (module de l'app) ────────────"
cd "${INSTALL_DIR}" 2>/dev/null || true
"$PY" - <<'PY'
import os, sys
# Modèle en couches : base/ (import panel) puis racine (import app) sur le chemin.
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, "base"))
sys.path.insert(0, ROOT)
try:
    from panel import create_app          # fondation (base/)
    from app import maps                   # module métier d'estimation (app/)
    app = create_app()
    with app.app_context():
        print("  Estimation activée (maps_enabled) :", maps.is_enabled())
        dep, arr = "Gare du Grau-du-Roi", "Aigues-Mortes"
        res, raison = maps.estimate_or_reason(dep, arr)
        print(f"  Test : « {dep} » → « {arr} »")
        print("    Résultat :", res)
        print("    Détail   :", raison or "itinéraire routier OK")
except Exception:
    import traceback; traceback.print_exc()
PY

echo
echo "Lecture :"
echo "  • Tous « OK ✓ » + un résultat  → l'estimation fonctionne."
echo "  • OSRM en ÉCHEC mais BAN OK     → tu auras une estimation APPROXIMATIVE (normal)."
echo "  • Tout en ÉCHEC                 → le serveur n'a pas d'accès Internet sortant."
echo "  • « maps_enabled : False »      → réactive-la dans Réglages → Estimation."
