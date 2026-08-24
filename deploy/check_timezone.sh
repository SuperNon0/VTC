#!/usr/bin/env bash
#
# VTC — vérifier le fuseau horaire de la machine.
# Les dates/heures des courses utilisent l'heure LOCALE du serveur : si le fuseau
# est faux, les horaires seront décalés. Cette commande montre l'état réel.
#
#   sudo bash /opt/vtc/deploy/check_timezone.sh
#
set -euo pipefail

INSTALL_DIR="/opt/vtc"
PY="${INSTALL_DIR}/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "──────────── Horloge système ────────────"
if timedatectl show >/dev/null 2>&1; then
  timedatectl | grep -E "Time zone|Local time|Universal|synchronized" || true
else
  echo "  Fuseau : $(cat /etc/timezone 2>/dev/null || echo inconnu)"
  echo "  Heure locale : $(date '+%Y-%m-%d %H:%M:%S %Z')"
fi

echo
echo "──────────── Vu par l'application (Python) ────────────"
"$PY" - <<'PY'
import time, datetime
now = datetime.datetime.now()
print("  Heure locale de l'app :", now.strftime("%Y-%m-%d %H:%M:%S (%A)"))
print("  Nom du fuseau         :", "/".join(dict.fromkeys(time.tzname)))
off = -time.timezone // 3600
print("  Décalage vs UTC       :", ("+" if off >= 0 else "") + str(off) + " h "
      "(hiver ; +1 h de plus en été)")
PY

echo
echo "Si le fuseau n'est pas le bon (France = Europe/Paris) :"
echo "    sudo timedatectl set-timezone Europe/Paris"
echo "    sudo systemctl restart vtc      # pour que l'app reprenne le bon fuseau"
