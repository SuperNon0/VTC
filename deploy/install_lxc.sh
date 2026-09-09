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
REPO_REF="${REPO_REF:-}"   # branche ou tag à installer (optionnel)
BIND="${BIND:-}"          # adresse d'écoute gunicorn (ex. 0.0.0.0:8000). Vide → défaut 127.0.0.1:8000

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
        git -C "${INSTALL_DIR}" fetch origin "${REPO_REF:-HEAD}"
        git -C "${INSTALL_DIR}" checkout -q FETCH_HEAD
    else
        git clone ${REPO_REF:+--branch "${REPO_REF}"} "${REPO_URL}" "${INSTALL_DIR}"
    fi
fi
mkdir -p "${INSTALL_DIR}/data"

# Modèle en couches : un PROJET ne versionne PAS base/. Si la fondation n'est pas
# présente (dépôt app-only), on l'amorce depuis le dépôt site-base.
if [ ! -d "${INSTALL_DIR}/base/panel" ] && [ -f "${INSTALL_DIR}/bootstrap_base.py" ]; then
    echo ">>> [3b/6] Amorçage de la couche base (bootstrap_base.py)"
    (cd "${INSTALL_DIR}" && python3 bootstrap_base.py)
fi

echo ">>> [4/6] Venv Python + dépendances"
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo ">>> [5/6] .env"
# Compte admin d'emblée : ADMIN_EMAIL / ADMIN_PASSWORD (alias SUPERADMIN_*).
ADMIN_EMAIL="${ADMIN_EMAIL:-${SUPERADMIN_EMAIL:-}}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-${SUPERADMIN_PASSWORD:-}}"
# S'il n'a pas été fourni et qu'un terminal est disponible, on le demande.
if [ -z "${ADMIN_EMAIL}" ] && [ -t 0 ]; then
    read -rp ">>> E-mail Google du compte admin (Entrée pour aucun) : " ADMIN_EMAIL || true
    ADMIN_EMAIL="$(printf '%s' "${ADMIN_EMAIL}" | tr -d '[:space:]')"
fi
GENERATED_PWD=""
if [ -z "${ADMIN_PASSWORD}" ]; then
    ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
    GENERATED_PWD="${ADMIN_PASSWORD}"
fi
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
    KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${KEY}|" "${INSTALL_DIR}/.env"
    sed -i "s|^SUPERADMIN_EMAIL=.*|SUPERADMIN_EMAIL=${ADMIN_EMAIL}|" "${INSTALL_DIR}/.env"
    sed -i "s|^SUPERADMIN_PASSWORD=.*|SUPERADMIN_PASSWORD=${ADMIN_PASSWORD}|" "${INSTALL_DIR}/.env"
    echo "   .env créé (super-admin ${ADMIN_EMAIL:-sans e-mail} amorcé)."
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 640 "${INSTALL_DIR}/.env"

echo ">>> [6/6] systemd"
cp "${INSTALL_DIR}/deploy/site-base.service" /etc/systemd/system/site-base.service
# Écoute personnalisée (BIND) : ex. 0.0.0.0:8000 pour un accès par l'IP du conteneur.
# Surcharge propre (survit aux mises à jour) ; sinon on garde le 127.0.0.1 par défaut.
if [ -n "${BIND}" ]; then
    mkdir -p /etc/systemd/system/site-base.service.d
    printf '[Service]\nExecStart=\nExecStart=%s/.venv/bin/gunicorn -w 2 -b %s wsgi:app\n' \
        "${INSTALL_DIR}" "${BIND}" > /etc/systemd/system/site-base.service.d/override.conf
    echo "   écoute sur ${BIND}."
fi
systemctl daemon-reload
systemctl enable site-base.service

echo ">>> [note] Bouton « Mettre à jour » : aucun sudo requis."
# Le rechargement se fait par SIGHUP au master gunicorn (le service se recharge
# lui-même), et git/pip tournent sans sudo car /opt/site-base appartient à
# ${SERVICE_USER}. Rien à configurer côté sudoers.

echo ">>> [démarrage] service"
systemctl restart site-base || true

echo ""
echo "════════════════════════════════════════════════════════════════"
echo " Installation terminée — le service tourne (127.0.0.1:8000)."
if [ -n "${ADMIN_EMAIL}" ]; then
  echo " Super-admin (Cloudflare)   : ${ADMIN_EMAIL}"
fi
if [ -n "${GENERATED_PWD}" ]; then
  echo " Mot de passe admin (LAN)   : ${GENERATED_PWD}   ← généré, note-le !"
  echo "   (à changer via Paramètres → Mot de passe, ou deploy/reset_admin.sh)"
fi
echo "════════════════════════════════════════════════════════════════"
echo " Étapes restantes :"
echo "  • Exposer via Cloudflare Tunnel (voir docs/deploiement-proxmox.md)"
echo "  • Régler l'accès Cloudflare dans l'UI (Paramètres → Cloudflare / Accès)"
echo "  • Rattacher/changer l'e-mail admin : deploy/set_email.sh <email>"
echo "  • Logs : journalctl -u site-base -f"
