#!/usr/bin/env bash
#
# Site de base — installation en une commande (Debian/Ubuntu, LXC ou VM), en root.
#
#   ADMIN_EMAIL=toi@gmail.com bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/Site-base/main/install.sh)"
#
# Options (variables d'environnement) :
#   ADMIN_EMAIL=...      e-mail Google du super-admin (Cloudflare)
#   ADMIN_PASSWORD=...   mot de passe admin LAN (sinon généré aléatoirement)
#   REPO_URL=...         dépôt à installer (défaut : SuperNon0/Site-base)
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/SuperNon0/Site-base.git}"
INSTALL_DIR="/opt/site-base"

if [ "$(id -u)" -ne 0 ]; then
  echo "À lancer en root (ou via sudo)." >&2
  exit 1
fi

echo ">>> Dépendances minimales (git)"
apt-get update -y
apt-get install -y --no-install-recommends git ca-certificates

echo ">>> Récupération du code (${REPO_URL})"
if [ -d "${INSTALL_DIR}/.git" ]; then
  git -C "${INSTALL_DIR}" pull --ff-only
else
  git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
fi

# ADMIN_EMAIL / ADMIN_PASSWORD sont transmis par l'environnement au script LXC.
export ADMIN_EMAIL="${ADMIN_EMAIL:-}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

echo ">>> Installation"
bash "${INSTALL_DIR}/deploy/install_lxc.sh"
