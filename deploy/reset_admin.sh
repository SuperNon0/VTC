#!/usr/bin/env bash
#
# Site de base — réinitialiser le mot de passe du super-admin (accès LAN).
#   sudo bash /opt/site-base/deploy/reset_admin.sh
#   sudo bash /opt/site-base/deploy/reset_admin.sh "NouveauMotDePasse!"
#
set -euo pipefail

INSTALL_DIR="/opt/site-base"
SERVICE_USER="sitebase"

cd "${INSTALL_DIR}"
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/manage.py" reset_admin "$@"

echo "→ Reconnecte-toi en local avec le nouveau mot de passe."
