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

### Installation express (une commande, zéro réglage après)

Dans le conteneur (ou la VM), en root — passe ton e-mail Google directement, le
super-admin est créé d'emblée :

```bash
ADMIN_EMAIL=toi@gmail.com bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/Site-base/main/install.sh)"
```

- Ajoute `ADMIN_PASSWORD=...` pour choisir le mot de passe LAN (sinon un mot de
  passe est **généré et affiché** en fin d'install — note-le).
- Le service démarre tout seul ; il reste à exposer via Cloudflare (§3) et à
  régler l'accès dans l'UI (§4).
- Si tu ne passes pas `ADMIN_EMAIL`, **l'installateur te le demande** au lancement
  (Entrée pour aucun). Tu pourras toujours le régler après (voir plus bas).

### Ou en deux temps (script d'install seul)

```bash
curl -fsSL https://raw.githubusercontent.com/SuperNon0/Site-base/main/deploy/install_lxc.sh \
  | bash -s -- https://github.com/SuperNon0/Site-base.git
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

Tu peux renseigner l'**équipe**, l'**AUD** et la **vérification JWT** de deux façons :

- **Depuis l'UI (recommandé)** : connecté en super-admin →
  **Paramètres → Cloudflare / Accès**. Ces réglages sont stockés en base et
  **priment sur le `.env`**. Le champ **Équipe** accepte le nom seul
  (`super-nono`) *ou* le domaine complet — il est normalisé automatiquement.
- **Ou dans `.env`** : `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `CF_VERIFY_JWT`
  (valeurs de secours si rien n'est réglé dans l'UI).

Un écran **Paramètres → Diagnostic** montre en direct : jeton reçu (oui/non),
e-mail d'en-tête, équipe/AUD, et le résultat de la vérif JWT (`OK ✓` / `échec ✗`)
avec le détail de l'erreur — pratique pour régler la configuration Access.

Après un changement dans `.env` (pas nécessaire pour l'UI), recharge le site :

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
| Mettre à jour (UI) | **Paramètres → Mise à jour → « Mettre à jour »** |
| Mettre à jour (CLI) | `sudo bash /opt/site-base/deploy/update.sh` |
| Sauvegarde | copier `/opt/site-base/data/site-base.db` (+ `.env`) |
| Snapshot Proxmox | `pct snapshot 120 avant-maj` (ou l'UI) |

### Bouton « Mettre à jour » depuis l'interface

Connecté en super-admin, **Paramètres → Mise à jour** affiche la **version en
cours** (tag `vX.Y.Z`) et l'état du service. Le bouton **« Mettre à jour »** :

1. `git fetch --tags` puis passage à la **dernière version publiée** (tag `vX.Y.Z`),
2. `pip install -r requirements.txt` (met à jour les dépendances),
3. **recharge le service** (SIGHUP à gunicorn), puis affiche `vX → vY`.

Le journal des opérations s'affiche en direct sous le bouton. Le modèle de
versions (tags, publication, rollback) est décrit dans
[`versions.md`](versions.md).

**Aucun sudo requis :**
- `/opt/site-base` appartient à l'utilisateur du service (`sitebase`) → `git`/`pip`
  se font **sans sudo**.
- Le rechargement se fait par **`SIGHUP` au master gunicorn** : le service se
  recharge **lui-même** (nouveaux workers avec le code à jour), sans coupure et
  **sans sudoers**.

> Endpoints correspondants (super-admin, `/api/*` en `no-store`, bloqués pendant
> une impersonation) : `GET /api/system/info`, `POST /api/system/update`,
> `POST /api/system/restart` — voir `panel/routes/system_routes.py`.
> En dev local (hors gunicorn), la mise à jour Git/pip fonctionne mais le
> rechargement automatique n'a pas lieu (relance `python run.py` à la main).

### Rattacher / changer l'e-mail Google de l'admin

Pour que ton compte local soit reconnu via Cloudflare (Google), rattache ton
e-mail. Trois façons :

- **Une commande serveur** (fusionne un éventuel doublon **sans rien perdre** —
  réattribue toutes les données par `compte_id` au compte de base) :

  ```bash
  sudo bash /opt/site-base/deploy/set_email.sh toi@gmail.com   # rattacher / fusionner
  sudo bash /opt/site-base/deploy/set_email.sh --clear         # détacher
  ```

- **Dans l'app** : Paramètres → **Mon e-mail Google** (l'UI demande de supprimer
  d'abord un compte en conflit ; la console, elle, fusionne).
- **À l'install** : via `ADMIN_EMAIL=...` (voir §2).

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
