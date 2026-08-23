#!/usr/bin/env bash
#
# Site de base — mise à jour depuis le dépôt Git puis redémarrage.
#   sudo bash /opt/site-base/deploy/update.sh
#
set -euo pipefail

INSTALL_DIR="/opt/site-base"

echo ">>> git pull"
git -C "${INSTALL_DIR}" pull --ff-only

echo ">>> dépendances"
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo ">>> redémarrage"
systemctl restart site-base

echo "OK — site-base mis à jour et redémarré."
