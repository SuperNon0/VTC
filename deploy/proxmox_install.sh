#!/usr/bin/env bash
#
# Crée un conteneur LXC Debian 12 sur l'hôte Proxmox ET installe VTC dedans.
# À lancer SUR L'HÔTE Proxmox (le nœud, ex. pve2), en root — PAS dans un conteneur.
#
#   ADMIN_EMAIL=toi@gmail.com bash -c "$(curl -fsSL \
#     https://raw.githubusercontent.com/SuperNon0/VTC/claude/migration-nouveau-socle/deploy/proxmox_install.sh)"
#
# Réglages (variables d'environnement — tout est optionnel sauf, idéalement, ADMIN_EMAIL) :
#   ADMIN_EMAIL=...    e-mail Google du super-admin (Cloudflare). Sinon demandé/aucun.
#   ADMIN_PASSWORD=... mot de passe admin LAN (sinon généré par l'install).
#   CTID=...           numéro du conteneur (défaut : prochain libre).
#   HOSTNAME_CT=vtc    nom d'hôte du conteneur.
#   STORAGE=local-lvm  stockage du disque du conteneur (voir `pvesm status`).
#   BRIDGE=vmbr0       pont réseau (voir `ip link` / la config réseau Proxmox).
#   CORES / MEMORY / SWAP / DISK   ressources (défaut : 1 / 512 Mo / 512 Mo / 4 Go).
#   BIND=0.0.0.0:8000  adresse d'écoute (par défaut : accessible par l'IP du CT).
#   REPO_URL / REPO_REF  dépôt et branche/tag VTC à installer.
#
set -euo pipefail

if ! command -v pct >/dev/null 2>&1; then
  echo "✗ 'pct' introuvable : lance ce script SUR L'HÔTE Proxmox (le nœud), pas dans un conteneur." >&2
  exit 1
fi

CTID="${CTID:-$(pvesh get /cluster/nextid)}"
HOSTNAME_CT="${HOSTNAME_CT:-vtc}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
BRIDGE="${BRIDGE:-vmbr0}"
CORES="${CORES:-1}"; MEMORY="${MEMORY:-512}"; SWAP="${SWAP:-512}"; DISK="${DISK:-4}"
BIND="${BIND:-0.0.0.0:8000}"
REPO_URL="${REPO_URL:-https://github.com/SuperNon0/VTC.git}"
REPO_REF="${REPO_REF:-claude/migration-nouveau-socle}"
ADMIN_EMAIL="${ADMIN_EMAIL:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

# --- Vérifs préliminaires : le stockage et le pont existent-ils ? ---
if ! pvesm status --storage "${STORAGE}" >/dev/null 2>&1; then
  echo "✗ Stockage « ${STORAGE} » introuvable. Choisis-en un avec :  pvesm status" >&2
  echo "   puis relance :  STORAGE=<ton-stockage> ... bash proxmox_install.sh" >&2
  exit 1
fi

# --- Template Debian 12 (téléchargé si absent) ---
echo ">>> [1/6] Template Debian 12"
TMPL="$(pveam list "${TEMPLATE_STORAGE}" 2>/dev/null | awk '/debian-12-standard/{print $1}' | tail -1 || true)"
if [ -z "${TMPL}" ]; then
  echo "    Téléchargement du template…"
  pveam update >/dev/null 2>&1 || true
  NAME="$(pveam available --section system 2>/dev/null | awk '/debian-12-standard/{print $NF}' | sort -V | tail -1)"
  if [ -z "${NAME}" ]; then echo "✗ Aucun template debian-12-standard disponible." >&2; exit 1; fi
  pveam download "${TEMPLATE_STORAGE}" "${NAME}"
  TMPL="${TEMPLATE_STORAGE}:vztmpl/${NAME}"
fi
echo "    Template : ${TMPL}"

# --- Création + démarrage du conteneur ---
echo ">>> [2/6] Création du conteneur ${CTID} (${HOSTNAME_CT})"
pct create "${CTID}" "${TMPL}" \
  --hostname "${HOSTNAME_CT}" \
  --cores "${CORES}" --memory "${MEMORY}" --swap "${SWAP}" \
  --rootfs "${STORAGE}:${DISK}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
  --unprivileged 1 --features nesting=1 --onboot 1

echo ">>> [3/6] Démarrage + attente réseau"
pct start "${CTID}"
IP=""
for _ in $(seq 1 30); do
  IP="$(pct exec "${CTID}" -- hostname -I 2>/dev/null | awk '{print $1}')" || true
  [ -n "${IP}" ] && break
  sleep 2
done
[ -z "${IP}" ] && echo "    (IP pas encore visible — on continue quand même)"

echo ">>> [4/6] Dépendances de base dans le conteneur"
pct exec "${CTID}" -- bash -c "apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates"

# --- Install de VTC DANS le conteneur (script poussé, pas de curl imbriqué) ---
echo ">>> [5/6] Installation de VTC dans le conteneur"
TMPSH="$(mktemp)"
curl -fsSL "https://raw.githubusercontent.com/SuperNon0/VTC/${REPO_REF}/install.sh" -o "${TMPSH}"
pct push "${CTID}" "${TMPSH}" /root/install.sh
pct exec "${CTID}" -- env \
  ADMIN_EMAIL="${ADMIN_EMAIL}" ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  REPO_URL="${REPO_URL}" REPO_REF="${REPO_REF}" \
  bash /root/install.sh
rm -f "${TMPSH}"

# --- Écoute sur l'IP du conteneur (accès LAN par IP) ---
echo ">>> [6/6] Écoute sur ${BIND} (accès par l'IP du conteneur)"
TMPOV="$(mktemp)"
printf '[Service]\nExecStart=\nExecStart=/opt/site-base/.venv/bin/gunicorn -w 2 -b %s wsgi:app\n' "${BIND}" > "${TMPOV}"
pct exec "${CTID}" -- mkdir -p /etc/systemd/system/site-base.service.d
pct push "${CTID}" "${TMPOV}" /etc/systemd/system/site-base.service.d/override.conf
pct exec "${CTID}" -- systemctl daemon-reload
pct exec "${CTID}" -- systemctl restart site-base
rm -f "${TMPOV}"

IP="$(pct exec "${CTID}" -- hostname -I 2>/dev/null | awk '{print $1}')" || true
echo ""
echo "════════════════════════════════════════════════════════════════"
echo " Conteneur ${CTID} (${HOSTNAME_CT}) prêt — VTC installé et démarré."
echo " Accès    : http://${IP:-<IP-du-conteneur>}:8000"
echo " Console  : pct enter ${CTID}    |    Logs : pct exec ${CTID} -- journalctl -u site-base -f"
echo " Le mot de passe admin LAN a été affiché par l'install ci-dessus (note-le)."
echo "════════════════════════════════════════════════════════════════"
