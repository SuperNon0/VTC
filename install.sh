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
#   REPO_REF=...         branche ou tag à installer (défaut : branche par défaut du dépôt)
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/SuperNon0/Site-base.git}"
REPO_REF="${REPO_REF:-}"
INSTALL_DIR="/opt/site-base"

if [ "$(id -u)" -ne 0 ]; then
  echo "À lancer en root (ou via sudo)." >&2
  exit 1
fi

echo ">>> Dépendances minimales (git)"
apt-get update -y
apt-get install -y --no-install-recommends git ca-certificates

echo ">>> Récupération du code (${REPO_URL}${REPO_REF:+ @ ${REPO_REF}})"
if [ -d "${INSTALL_DIR}/.git" ]; then
  git -C "${INSTALL_DIR}" fetch --depth 1 origin "${REPO_REF:-HEAD}"
  git -C "${INSTALL_DIR}" checkout -q FETCH_HEAD
else
  git clone --depth 1 ${REPO_REF:+--branch "${REPO_REF}"} "${REPO_URL}" "${INSTALL_DIR}"
fi

# ADMIN_EMAIL / ADMIN_PASSWORD / REPO_REF sont transmis par l'environnement au script LXC.
export ADMIN_EMAIL="${ADMIN_EMAIL:-}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
export REPO_REF

echo ">>> Installation"
bash "${INSTALL_DIR}/deploy/install_lxc.sh"
