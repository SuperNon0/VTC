#!/usr/bin/env bash
#
# Site de base — réinitialiser le mot de passe du super-admin (accès LAN).
#   sudo bash /opt/vtc/deploy/reset_admin.sh
#   sudo bash /opt/vtc/deploy/reset_admin.sh "NouveauMotDePasse!"
#
set -euo pipefail

INSTALL_DIR="/opt/vtc"
SERVICE_USER="vtc"

cd "${INSTALL_DIR}"
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/python" -m panel.reset_admin "$@"

echo "→ Reconnecte-toi en local avec le nouveau mot de passe."
