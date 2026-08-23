#!/usr/bin/env bash
#
# Site de base — installation dans un conteneur LXC (Debian/Ubuntu).
# Inspiré du script d'install de BotPanel.
#
# À exécuter DANS le conteneur, en root :
#   # avec un dépôt distant :
#   curl -fsSL https://raw.githubusercontent.com/<user>/site-base/main/deploy/install_lxc.sh | bash -s -- https://github.com/<user>/site-base.git
#   # ou en local après avoir copié le repo dans /opt/site-base :
#   sudo bash deploy/install_lxc.sh
#
set -euo pipefail

INSTALL_DIR="/opt/site-base"
SERVICE_USER="sitebase"
REPO_URL="${1:-}"

echo ">>> [1/6] Dépendances système"
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip git ca-certificates

echo ">>> [2/6] Utilisateur système"
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --shell /usr/sbin/nologin --home "${INSTALL_DIR}" "${SERVICE_USER}"
fi

echo ">>> [3/6] Code source"
if [ -n "${REPO_URL}" ]; then
    if [ -d "${INSTALL_DIR}/.git" ]; then
        git -C "${INSTALL_DIR}" pull
    else
        git clone "${REPO_URL}" "${INSTALL_DIR}"
    fi
fi
mkdir -p "${INSTALL_DIR}/data"

echo ">>> [4/6] Venv Python + dépendances"
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo ">>> [5/6] .env"
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
    # Génère une SECRET_KEY aléatoire
    KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${KEY}|" "${INSTALL_DIR}/.env"
    echo "!! Édite ${INSTALL_DIR}/.env (SUPERADMIN_PASSWORD/EMAIL, Cloudflare, BotPanel) avant de démarrer."
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 640 "${INSTALL_DIR}/.env"

echo ">>> [6/6] systemd"
cp "${INSTALL_DIR}/deploy/site-base.service" /etc/systemd/system/site-base.service
systemctl daemon-reload
systemctl enable site-base.service

echo ""
echo "Installation terminée."
echo "  1. Éditer ${INSTALL_DIR}/.env"
echo "  2. systemctl start site-base"
echo "  3. journalctl -u site-base -f   (pour suivre les logs)"
echo "  4. Exposer via Cloudflare Tunnel (voir docs/deploiement-proxmox.md)"
