#!/usr/bin/env bash
#
# install.sh — Déploiement 1-commande du hub super-nono.cc dans un LXC Proxmox.
# À LANCER SUR LE SHELL DU NODE PROXMOX.
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/site/main/install.sh)"
#
# Options : CTID=130 CT_STORAGE=local-zfs ADMIN_PASSWORD=... bash -c "$(curl ...)"
#
set -euo pipefail

REPO_URL="https://github.com/SuperNon0/site.git"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="/opt/site-base"

CTID="${CTID:-}"
HOSTNAME_CT="${HOSTNAME_CT:-hub}"
TPL_PREFIX="debian-12-standard"
RAM_MB="${RAM_MB:-1024}"; CORES="${CORES:-2}"; DISK_GB="${DISK_GB:-6}"
BRIDGE="${BRIDGE:-vmbr0}"
CT_STORAGE="${CT_STORAGE:-local-lvm}"; TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
CT_IP="${CT_IP:-dhcp}"; CT_GW="${CT_GW:-}"
CT_PASSWORD="${CT_PASSWORD:-}"
HUB_PORT="${HUB_PORT:-8000}"
# Mot de passe du super-admin (login local LAN). Généré si vide.
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
# E-mail Google du super-admin (pour être reconnu via Cloudflare). Optionnel.
ADMIN_EMAIL="${ADMIN_EMAIL:-}"
# Marque affichée (logo = prefix doré + suffix italique) + badge.
BRAND_PREFIX="${BRAND_PREFIX:-super}"; BRAND_SUFFIX="${BRAND_SUFFIX:--nono}"; BRAND_BADGE="${BRAND_BADGE:-hub}"

RED=$'\e[31m';GRN=$'\e[32m';YLW=$'\e[33m';BLU=$'\e[34m';BLD=$'\e[1m';RST=$'\e[0m'
info(){ echo "${BLU}${BLD}[i]${RST} $*"; }
ok(){ echo "${GRN}${BLD}[✓]${RST} $*"; }
die(){ echo "${RED}${BLD}[✗]${RST} $*" >&2; exit 1; }

command -v pct >/dev/null 2>&1 || die "'pct' introuvable. Lance ce script SUR LE NODE PROXMOX."
[ "$(id -u)" -eq 0 ] || die "À lancer en root."

[ -z "$CTID" ] && CTID="$(pvesh get /cluster/nextid)"
pct status "$CTID" >/dev/null 2>&1 && die "Le conteneur $CTID existe déjà."
info "Conteneur cible : CTID=$CTID  hostname=$HOSTNAME_CT"

pveam update >/dev/null 2>&1 || true
TEMPLATE_FILE="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk '{print $1}' | grep "/${TPL_PREFIX}" | head -n1 || true)"
if [ -z "$TEMPLATE_FILE" ]; then
  AVAIL="$(pveam available --section system | awk '{print $2}' | grep "^${TPL_PREFIX}" | sort | tail -n1)"
  [ -n "$AVAIL" ] || die "Template Debian 12 introuvable."
  info "Téléchargement du template $AVAIL…"; pveam download "$TEMPLATE_STORAGE" "$AVAIL"
  TEMPLATE_FILE="${TEMPLATE_STORAGE}:vztmpl/${AVAIL}"
fi
ok "Template : $TEMPLATE_FILE"

[ -z "$CT_PASSWORD" ] && { CT_PASSWORD="$(openssl rand -base64 12)"; GEN_ROOT=1; }
[ -z "$ADMIN_PASSWORD" ] && { ADMIN_PASSWORD="$(openssl rand -base64 9 | tr -d '/+=')"; }

if [ "$CT_IP" = "dhcp" ]; then NETCFG="name=eth0,bridge=${BRIDGE},ip=dhcp";
else [ -n "$CT_GW" ] || die "IP statique sans passerelle (CT_GW)."; NETCFG="name=eth0,bridge=${BRIDGE},ip=${CT_IP},gw=${CT_GW}"; fi

info "Création du conteneur LXC…"
pct create "$CTID" "$TEMPLATE_FILE" \
  --hostname "$HOSTNAME_CT" --cores "$CORES" --memory "$RAM_MB" --swap "$RAM_MB" \
  --rootfs "${CT_STORAGE}:${DISK_GB}" --net0 "$NETCFG" --unprivileged 1 \
  --password "$CT_PASSWORD" --onboot 1 --description "Hub super-nono.cc"
ok "Conteneur $CTID créé."
pct start "$CTID"

info "Attente d'une IP…"
CT_IP_ADDR=""
for _ in $(seq 1 30); do CT_IP_ADDR="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"; [ -n "$CT_IP_ADDR" ] && break; sleep 2; done
[ -n "$CT_IP_ADDR" ] || die "Pas d'IP obtenue."
ok "IP : $CT_IP_ADDR"

info "Installation de Python + du hub (1-3 min)…"
INNER="$(cat <<INNER
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git ca-certificates sudo >/dev/null
id sitebase >/dev/null 2>&1 || useradd --system --shell /usr/sbin/nologin --home ${INSTALL_DIR} sitebase
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" ${INSTALL_DIR} >/dev/null 2>&1
mkdir -p ${INSTALL_DIR}/data
python3 -m venv ${INSTALL_DIR}/.venv
${INSTALL_DIR}/.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1
${INSTALL_DIR}/.venv/bin/pip install -q -r ${INSTALL_DIR}/requirements.txt >/dev/null 2>&1

SECRET=\$(python3 -c 'import secrets;print(secrets.token_hex(32))')
cat > ${INSTALL_DIR}/.env <<ENV
SECRET_KEY=\${SECRET}
SESSION_COOKIE_SECURE=false
BRAND_PREFIX=${BRAND_PREFIX}
BRAND_SUFFIX=${BRAND_SUFFIX}
BRAND_BADGE=${BRAND_BADGE}
DATABASE_PATH=${INSTALL_DIR}/data/site-base.db
SUPERADMIN_PASSWORD=${ADMIN_PASSWORD}
SUPERADMIN_EMAIL=${ADMIN_EMAIL}
CF_VERIFY_JWT=false
ALLOW_LOCAL_LOGIN=true
BOTPANEL_URL=
ENV
chmod 640 ${INSTALL_DIR}/.env

# service systemd (bind 0.0.0.0 pour l'accès LAN / reverse proxy)
sed 's|127.0.0.1:8000|0.0.0.0:${HUB_PORT}|' ${INSTALL_DIR}/deploy/site-base.service > /etc/systemd/system/site-base.service
chown -R sitebase:sitebase ${INSTALL_DIR}
systemctl daemon-reload
systemctl enable --now site-base >/dev/null 2>&1

# Helper de mise à jour depuis l'UI (lancé en root via sudo par l'app sitebase)
cat > /usr/local/bin/site-base-update <<'UPD'
#!/usr/bin/env bash
set -e
cd /opt/site-base
sudo -u sitebase git pull --ff-only
sudo -u sitebase /opt/site-base/.venv/bin/pip install -q -r requirements.txt
systemd-run --no-block --on-active=2 --collect systemctl restart site-base
UPD
chmod 755 /usr/local/bin/site-base-update
echo 'sitebase ALL=(root) NOPASSWD: /usr/local/bin/site-base-update' > /etc/sudoers.d/site-base-update
chmod 440 /etc/sudoers.d/site-base-update
INNER
)"
pct exec "$CTID" -- bash -c "$INNER"
ok "Hub installé et démarré."

echo
echo "${GRN}${BLD}══════════════════════════════════════════════════════════════${RST}"
echo "${GRN}${BLD}  Hub super-nono.cc prêt ! 🎉${RST}"
echo "${GRN}${BLD}══════════════════════════════════════════════════════════════${RST}"
echo
echo "  ${BLD}Accès web${RST}       : ${BLU}http://${CT_IP_ADDR}:${HUB_PORT}${RST}"
echo "  ${BLD}Conteneur LXC${RST}   : CTID ${CTID}  (hostname : ${HOSTNAME_CT})"
echo "  ${BLD}Login SSH/console${RST}: root${GEN_ROOT:+  /  mot de passe : ${YLW}${CT_PASSWORD}${RST}}"
echo "  ${BLD}Mot de passe SUPER-ADMIN${RST} (login local du hub) : ${YLW}${ADMIN_PASSWORD}${RST}"
echo
echo "  Pointe ton reverse proxy (super-nono.cc) vers ${CT_IP_ADDR}:${HUB_PORT}."
echo "  Cloudflare Zero Trust : renseigne CF_ACCESS_TEAM_DOMAIN + CF_ACCESS_AUD"
echo "  dans ${INSTALL_DIR}/.env et passe CF_VERIFY_JWT=true (voir docs/deploiement-proxmox.md)."
echo "  Mise à jour : pct enter ${CTID}  puis  bash ${INSTALL_DIR}/deploy/update.sh"
echo
