#!/usr/bin/env bash
#
# Installation VTC — DEUX MODES détectés automatiquement :
#
#   • Sur le NŒUD PROXMOX (commande « pct » présente) :
#       crée un conteneur LXC Debian 12 ET installe VTC dedans.
#   • Dans un conteneur / une VM déjà prête (« pct » absent) :
#       installe l'application en place.
#
#   Une commande, sur le shell du nœud Proxmox :
#     ADMIN_EMAIL=toi@gmail.com \
#       bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/VTC/main/install.sh)"
#
# Options (variables d'environnement, toutes optionnelles) :
#   ADMIN_EMAIL=...     e-mail Google du super-admin (Cloudflare).
#   ADMIN_PASSWORD=...  mot de passe admin LAN (sinon généré par l'install).
#   REPO_URL=...        dépôt VTC (défaut : SuperNon0/VTC).
#   REPO_REF=...        branche ou tag à installer (défaut : main).
#   BIND=...            adresse d'écoute (défaut : 0.0.0.0:8000, accès par IP).
#   (mode Proxmox) CTID, HOSTNAME_CT, STORAGE, BRIDGE, CORES, MEMORY, SWAP, DISK.
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/SuperNon0/VTC.git}"
REPO_REF="${REPO_REF:-main}"
INSTALL_DIR="/opt/site-base"
BIND="${BIND:-0.0.0.0:8000}"

# ═══════════════════════════ MODE NŒUD PROXMOX ═══════════════════════════
# Détection : sur l'hyperviseur, la commande « pct » existe ; dans un conteneur,
# non. On crée alors le CT et on relance CE MÊME script à l'intérieur.
if command -v pct >/dev/null 2>&1; then
  [ "$(id -u)" -eq 0 ] || { echo "✗ À lancer en root sur le nœud Proxmox." >&2; exit 1; }

  CTID="${CTID:-$(pvesh get /cluster/nextid)}"
  HOSTNAME_CT="${HOSTNAME_CT:-vtc}"
  STORAGE="${STORAGE:-local-lvm}"; TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
  BRIDGE="${BRIDGE:-vmbr0}"
  CORES="${CORES:-2}"; MEMORY="${MEMORY:-1024}"; SWAP="${SWAP:-1024}"; DISK="${DISK:-6}"

  pct status "$CTID" >/dev/null 2>&1 && { echo "✗ Le conteneur $CTID existe déjà (choisis un autre CTID=)." >&2; exit 1; }
  pvesm status --storage "$STORAGE" >/dev/null 2>&1 || {
    echo "✗ Stockage « $STORAGE » introuvable. Liste : pvesm status  → relance avec STORAGE=<ton-stockage>." >&2; exit 1; }

  echo ">>> [1/5] Template Debian 12"
  TMPL="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk '/debian-12-standard/{print $1}' | tail -1 || true)"
  if [ -z "$TMPL" ]; then
    echo "    Téléchargement du template…"
    pveam update >/dev/null 2>&1 || true
    NAME="$(pveam available --section system 2>/dev/null | awk '/debian-12-standard/{print $NF}' | sort -V | tail -1)"
    [ -n "$NAME" ] || { echo "✗ Template debian-12-standard indisponible." >&2; exit 1; }
    pveam download "$TEMPLATE_STORAGE" "$NAME"
    TMPL="${TEMPLATE_STORAGE}:vztmpl/${NAME}"
  fi

  echo ">>> [2/5] Création du conteneur $CTID ($HOSTNAME_CT)"
  pct create "$CTID" "$TMPL" --hostname "$HOSTNAME_CT" \
    --cores "$CORES" --memory "$MEMORY" --swap "$SWAP" \
    --rootfs "${STORAGE}:${DISK}" --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
    --unprivileged 1 --features nesting=1 --onboot 1
  pct start "$CTID"

  echo ">>> [3/5] Attente du réseau…"
  IP=""
  for _ in $(seq 1 30); do
    IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')" || true
    [ -n "$IP" ] && break; sleep 2
  done

  echo ">>> [4/5] Dépendances de base dans le conteneur"
  pct exec "$CTID" -- bash -c "apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates"

  echo ">>> [5/5] Installation de VTC dans le conteneur"
  TMPSH="$(mktemp)"
  curl -fsSL "https://raw.githubusercontent.com/SuperNon0/VTC/${REPO_REF}/install.sh" -o "$TMPSH"
  pct push "$CTID" "$TMPSH" /root/install.sh
  rm -f "$TMPSH"
  pct exec "$CTID" -- env \
    ADMIN_EMAIL="${ADMIN_EMAIL:-}" ADMIN_PASSWORD="${ADMIN_PASSWORD:-}" \
    REPO_URL="$REPO_URL" REPO_REF="$REPO_REF" BIND="$BIND" \
    bash /root/install.sh

  IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')" || true
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo " VTC prêt ! 🎉  Conteneur LXC $CTID (hostname : $HOSTNAME_CT)"
  echo " Accès web : http://${IP:-<IP-du-conteneur>}:8000"
  echo " Console   : pct enter $CTID     Logs : pct exec $CTID -- journalctl -u site-base -f"
  echo " (le mot de passe admin LAN a été affiché juste au-dessus — note-le)"
  echo "════════════════════════════════════════════════════════════════"
  exit 0
fi

# ═════════════════════ MODE DANS LE CONTENEUR / LA VM ═════════════════════
[ "$(id -u)" -eq 0 ] || { echo "✗ À lancer en root." >&2; exit 1; }

echo ">>> Dépendances minimales (git)"
apt-get update -y
apt-get install -y --no-install-recommends git ca-certificates

echo ">>> Récupération du code (${REPO_URL} @ ${REPO_REF})"
if [ -d "${INSTALL_DIR}/.git" ]; then
  git -C "${INSTALL_DIR}" fetch --depth 1 origin "${REPO_REF}"
  git -C "${INSTALL_DIR}" checkout -q FETCH_HEAD
else
  git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" "${INSTALL_DIR}"
fi

# Transmis à deploy/install_lxc.sh (amorçage base/, .env, service systemd, écoute).
export ADMIN_EMAIL="${ADMIN_EMAIL:-}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
export REPO_REF
export BIND

echo ">>> Installation"
bash "${INSTALL_DIR}/deploy/install_lxc.sh"
