#!/usr/bin/env bash
#
# Site de base — mise à jour vers une VERSION (tag Git vX.Y.Z) puis redémarrage.
#
#   sudo bash /opt/site-base/deploy/update.sh            # dernière version publiée
#   sudo bash /opt/site-base/deploy/update.sh v1.2.0     # version précise (rollback)
#   sudo bash /opt/site-base/deploy/update.sh --no-restart
#
# Tant qu'aucun tag vX.Y.Z n'existe, on suit la tête de la branche courante.
set -euo pipefail

INSTALL_DIR="/opt/site-base"
SERVICE_USER="sitebase"
RESTART=true
TARGET=""

for arg in "$@"; do
  case "$arg" in
    --no-restart) RESTART=false ;;
    v[0-9]*|[0-9]*) TARGET="$arg" ;;   # v1.2.3 ou 1.2.3
  esac
done

echo "==> [$(date '+%H:%M:%S')] Mise à jour…"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

run() { sudo -u "${SERVICE_USER}" "$@"; }

echo "==> git fetch (commits + tags)…"
run git -C "${INSTALL_DIR}" fetch --tags --prune --force origin

# Choisit la cible : arg fourni, sinon dernier tag vX.Y.Z, sinon la branche.
if [ -z "${TARGET}" ]; then
  TARGET="$(run git -C "${INSTALL_DIR}" tag -l --sort=-v:refname | grep -E '^v?[0-9]' | head -1 || true)"
fi

if [ -n "${TARGET}" ]; then
  echo "==> Passage à la version ${TARGET}…"
  run git -C "${INSTALL_DIR}" -c advice.detachedHead=false checkout --force "${TARGET}"
else
  BRANCH="$(run git -C "${INSTALL_DIR}" rev-parse --abbrev-ref HEAD)"
  echo "==> Aucun tag de version — suivi de origin/${BRANCH}…"
  run git -C "${INSTALL_DIR}" reset --hard "origin/${BRANCH}"
fi

echo "==> Dépendances Python…"
run "${INSTALL_DIR}/.venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

if [ "$RESTART" = "true" ]; then
  echo "==> Redémarrage du service…"
  systemctl restart site-base
  sleep 2
  systemctl is-active site-base && echo "==> Service actif ✓" || echo "==> ERREUR : service inactif"
fi

echo "==> Version installée : $(run git -C "${INSTALL_DIR}" describe --tags --always)"
echo "==> [$(date '+%H:%M:%S')] Terminé."
