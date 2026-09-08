#!/usr/bin/env bash
#
# Site de base — rattache / retire l'e-mail Google du compte administrateur de base.
# Fusionne automatiquement un éventuel doublon (sans perdre de données).
#
#   sudo bash /opt/site-base/deploy/set_email.sh ton.email@gmail.com
#   sudo bash /opt/site-base/deploy/set_email.sh --clear
#
set -euo pipefail

INSTALL_DIR="/opt/site-base"
SERVICE_USER="sitebase"

if [ $# -lt 1 ]; then
  echo "Usage : $0 <email> | --clear"
  exit 1
fi

cd "${INSTALL_DIR}"
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/manage.py" set_email "$1"
