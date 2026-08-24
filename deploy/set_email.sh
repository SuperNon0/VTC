#!/usr/bin/env bash
#
# VTC — rattacher ton e-mail Google au compte super-admin (accès unifié).
# Réunit login local (mot de passe) + connexion Cloudflare (e-mail) sur UN compte,
# et fusionne au passage un éventuel doublon / le compte qui a déjà cet e-mail.
#
#   sudo bash /opt/vtc/deploy/set_email.sh ton.email@gmail.com
#   sudo bash /opt/vtc/deploy/set_email.sh --clear      # détacher l'e-mail
#
set -euo pipefail

INSTALL_DIR="/opt/vtc"
SERVICE_USER="vtc"

cd "${INSTALL_DIR}"
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/python" -m panel.set_email "$@"

echo "→ C'est le même compte : mot de passe OU Cloudflare avec cet e-mail."
