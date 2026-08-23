# Guide de déploiement — Proxmox + Cloudflare Zero Trust

Ce guide explique comment héberger le site de base dans **ton infrastructure
Proxmox**, derrière **Cloudflare Zero Trust**, avec les **notifications BotPanel**.

> **Ordre de priorité pour l'hébergement (à décider avec le développeur) :**
> 1. **LXC** (conteneur léger) — recommandé par défaut, faible empreinte.
> 2. **VM** — repli si un LXC ne convient pas (besoins noyau spécifiques,
>    isolation renforcée, montages particuliers…).
>
> Les deux font tourner exactement le même code (Flask + gunicorn + systemd).
> Seule la création du conteneur/VM change ; l'install applicative est identique.

---

## 0. Vue d'ensemble

```
                 Internet
                    │
                    ▼
         ┌────────────────────┐
         │  Cloudflare (WAF +  │   Zero Trust / Access = portier e-mail
         │   Zero Trust Access)│
         └─────────┬──────────┘
                   │  tunnel chiffré (cloudflared), aucune ouverture de port
                   ▼
   ┌───────────────────────────────┐   Proxmox (ton hyperviseur)
   │  LXC « site-base »            │
   │   gunicorn 127.0.0.1:8000     │◀── cloudflared (même conteneur)
   │   systemd: site-base.service  │
   └───────────────┬───────────────┘
                   │  POST /api/notify
                   ▼
   ┌───────────────────────────────┐
   │  LXC « botpanel » (Discord)   │
   └───────────────────────────────┘
```

Deux couches de sécurité **complémentaires** (voir `authentification-v2.md` §1) :
- **Cloudflare Access** décide *qui peut atteindre le site* (e-mail autorisé).
- **L'application** décide *ce qui se passe ensuite* (rôles, cycle de vie).

---

## 1. Créer le conteneur LXC (option recommandée)

Sur l'hôte Proxmox (shell du nœud) :

```bash
# Récupérer un template Debian 12 si besoin
pveam update
pveam available | grep debian-12
pveam download local debian-12-standard_12.7-1_amd64.tar.zst

# Créer le conteneur (adapte VMID, storage, bridge, IP)
pct create 120 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname site-base \
  --cores 1 --memory 512 --swap 512 \
  --rootfs local-lvm:4 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 --features nesting=1 \
  --onboot 1

pct start 120
pct exec 120 -- bash -c "apt-get update && apt-get install -y curl git"
```

> `nesting=1` évite les soucis avec systemd dans un LXC non privilégié.
> 512 Mo de RAM et 1 cœur suffisent largement pour ce site.

### Repli VM (si LXC impossible)

Crée une VM Debian 12 minimale (2 Go RAM, 10 Go disque) via l'assistant Proxmox
ou cloud-init, puis suis les mêmes étapes §2 → §5 à l'intérieur. Rien d'autre ne
change.

---

## 2. Installer l'application

Dans le conteneur (ou la VM), en root :

```bash
# Depuis ton dépôt Git
curl -fsSL https://raw.githubusercontent.com/<user>/site-base/main/deploy/install_lxc.sh \
  | bash -s -- https://github.com/<user>/site-base.git
```

Le script (`deploy/install_lxc.sh`) :
- installe Python + venv + dépendances,
- crée l'utilisateur système `sitebase`,
- copie `.env.example` → `.env` en générant une `SECRET_KEY` aléatoire,
- installe et active le service systemd `site-base.service`.

Puis édite la config :

```bash
nano /opt/site-base/.env
```

À renseigner au minimum :

```env
SECRET_KEY=<généré automatiquement>
SESSION_COOKIE_SECURE=true              # tu es derrière HTTPS Cloudflare
SUPERADMIN_PASSWORD=<mot de passe fort> # accès local LAN
SUPERADMIN_EMAIL=toi@gmail.com          # ton e-mail Google (autorisé dans CF)
CF_ACCESS_TEAM_DOMAIN=<ton-equipe>      # https://<ton-equipe>.cloudflareaccess.com
CF_ACCESS_AUD=<aud-tag-de-l-app>
CF_VERIFY_JWT=true
BOTPANEL_URL=http://192.168.1.20:8080   # ton BotPanel
```

Démarre :

```bash
systemctl start site-base
journalctl -u site-base -f
```

Le site écoute en local sur `127.0.0.1:8000` (jamais exposé directement).

---

## 3. Exposer via Cloudflare Tunnel (cloudflared)

Le tunnel évite d'ouvrir le moindre port : la connexion part **du conteneur vers
Cloudflare**. C'est aussi ce qui garantit que l'origine est **injoignable sans
Cloudflare** (protection clé, cf. `authentification-v2.md` §9.1).

```bash
# Dans le conteneur site-base
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
dpkg -i cloudflared.deb

cloudflared tunnel login                       # ouvre un lien à valider
cloudflared tunnel create site-base            # note l'UUID généré
```

Crée `/etc/cloudflared/config.yml` :

```yaml
tunnel: <UUID-du-tunnel>
credentials-file: /root/.cloudflared/<UUID-du-tunnel>.json

ingress:
  - hostname: monsite.exemple.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Route le DNS puis installe le service :

```bash
cloudflared tunnel route dns site-base monsite.exemple.com
cloudflared service install
systemctl enable --now cloudflared
```

> **Durcissement recommandé (spec §9.1) :** en plus du tunnel, tu peux configurer
> le pare-feu du conteneur pour n'accepter QUE le LAN sur le port 8000 (pour le
> login local par mot de passe) et rien d'autre. Le trafic public ne passe que
> par le tunnel.

---

## 4. Configurer Cloudflare Zero Trust (Access)

Dans le dashboard **Zero Trust → Access → Applications** :

1. **Add an application → Self-hosted.**
2. Domaine : `monsite.exemple.com`.
3. **Policies** : crée une policy *Allow* qui liste les **e-mails autorisés**
   (ou un domaine, un groupe…). C'est ici que tu ajoutes/retires qui peut
   *atteindre* le site.
4. Une fois l'app créée, ouvre son **Overview** et copie l'**Application Audience
   (AUD) Tag** → c'est la valeur `CF_ACCESS_AUD` de ton `.env`.
5. `CF_ACCESS_TEAM_DOMAIN` = le sous-domaine de ton équipe (la partie `<equipe>`
   de `https://<equipe>.cloudflareaccess.com`).

Redémarre le site après avoir renseigné ces deux valeurs :

```bash
systemctl restart site-base
```

### Comment ça marche ensuite

- Un e-mail **autorisé dans la policy** mais **inconnu de l'app** → page
  « Demander un accès » → crée un compte `pending` → tu le valides dans
  **Paramètres → Comptes**.
- Cloudflare ne connaît que « autorisé / refusé ». Les rôles, le blocage, la
  suppression, le « voir en tant que » sont **toujours** gérés par l'app.

> ⚠️ `CF_VERIFY_JWT=true` fait vérifier la signature du JWT `Cf-Access-Jwt-Assertion`
> contre les clés de ton équipe **et** contrôler l'`aud`. Sans ça, un attaquant
> joignant l'origine en direct pourrait forger l'en-tête e-mail. Ne le désactive
> que si l'origine est **strictement** injoignable hors Cloudflare.

---

## 5. BotPanel (notifications)

Le site poste sur `{BOTPANEL_URL}/api/notify`. Assure-toi que le conteneur
`site-base` atteint BotPanel sur ton LAN (même bridge / route). Crée les trois
notifications (`acces_demande`, `acces_valide`, `acces_bloque`) dans BotPanel —
voir [`notifications-botpanel.md`](notifications-botpanel.md).

Test rapide depuis le conteneur :

```bash
curl -X POST "$BOTPANEL_URL/api/notify" \
  -H "Content-Type: application/json" \
  -d '{"id":"acces_demande","vars":{"email":"test@gmail.com"}}'
```

---

## 6. Exploitation

| Action | Commande |
|---|---|
| Logs en direct | `journalctl -u site-base -f` |
| Redémarrer | `systemctl restart site-base` |
| Mettre à jour | `sudo bash /opt/site-base/deploy/update.sh` |
| Sauvegarde | copier `/opt/site-base/data/site-base.db` (+ `.env`) |
| Snapshot Proxmox | `pct snapshot 120 avant-maj` (ou l'UI) |

### Changer / réinitialiser le mot de passe admin

- **Depuis le site** : connecté en super-admin → **Paramètres → Mot de passe
  administrateur** (demande le mot de passe actuel).
- **Mot de passe oublié** (sur le serveur, sans être connecté) :

  ```bash
  sudo bash /opt/site-base/deploy/reset_admin.sh            # saisie masquée
  sudo bash /opt/site-base/deploy/reset_admin.sh "Nouveau!" # non interactif
  ```

Le super-admin reste toujours joignable **en LAN par mot de passe**. Le
**dernier super-admin est indestructible** (ni suppression ni rétrogradation)
pour éviter de se verrouiller dehors.

---

## 7. Checklist de déploiement

- [ ] Conteneur LXC (ou VM) créé, à jour.
- [ ] `install_lxc.sh` exécuté, service `site-base` actif.
- [ ] `.env` rempli : `SECRET_KEY`, `SUPERADMIN_*`, `CF_ACCESS_*`, `BOTPANEL_URL`.
- [ ] `SESSION_COOKIE_SECURE=true` et `CF_VERIFY_JWT=true` en production.
- [ ] Tunnel `cloudflared` actif, DNS routé, origine injoignable sans Cloudflare.
- [ ] Application Access créée + policy e-mails + AUD tag reporté dans `.env`.
- [ ] 3 notifications créées dans BotPanel, test `curl` OK.
- [ ] Connexion locale (LAN, mot de passe) et via Cloudflare (e-mail) testées.
