<div align="center">

# VTC — gestion d'activité taxi

**Application web (PWA)** de gestion des courses pour une équipe de conducteurs.
Un super-admin (également conducteur) et plusieurs conducteurs. Chacun a son
calendrier des courses **qui lui sont assignées**, reçoit une notification à
chaque nouvelle course, et peut créer une course et l'assigner à qui il veut.

Construite sur le template `SuperNon0/site` (thème « RecipeLog » + auth
**Cloudflare Zero Trust**).

</div>

---

## Sommaire

1. [Fonctionnalités](#fonctionnalités)
2. [Installation en local (développement / test)](#installation-en-local-développement--test)
3. [Installation en production (Proxmox + Cloudflare)](#installation-en-production-proxmox--cloudflare)
4. [Première configuration (super-admin)](#première-configuration-super-admin)
5. [Rôles et permissions](#rôles-et-permissions)
6. [Mise à jour du site](#mise-à-jour-du-site)
7. [Mot de passe oublié](#mot-de-passe-oublié)
8. [Documentation détaillée](#documentation-détaillée)

---

## Fonctionnalités

- 📅 **Calendrier personnel** — les courses assignées à venir, groupées par jour ;
  statut modifiable (à faire / en cours / terminée / annulée) directement.
- ➕ **Création de course** avec, dans un seul écran :
  - **Extraction IA** : coller le message d'un client → le nom, le téléphone et
    les adresses se remplissent automatiquement.
  - **Autocomplétion** des clients habitués.
  - **Boutons de lieux fréquents** (gares, aéroports…) sous départ et arrivée.
  - **Prix** par grille tarifaire préenregistrée, ou **« Autre »** (prix libre).
  - **Assignation** à n'importe quel conducteur → notification push automatique.
- 🤖 **Extraction IA configurable** — Gemini / Mistral / Groq (gratuits, sans
  carte bancaire). Fournisseur + clé réglables **dans l'app** (super-admin),
  sans redéploiement.
- 🔔 **Notifications Web Push (PWA)** — alerte à chaque course assignée. Android
  via Chrome ; iPhone (iOS 16.4+) après ajout à l'écran d'accueil.
- 💶 **Grilles tarifaires place-à-place** — un prix par trajet (lieu départ →
  lieu arrivée). **Sélection automatique** du tarif quand le départ et l'arrivée
  d'une course correspondent (super-admin gère les prix).
- 📍 **Lieux fréquents** — liste **collaborative** ; tape « gare… » dans une
  adresse pour la remplir automatiquement.
- 🗺️ **Estimation du trajet** — durée + distance via OpenStreetMap (gratuit, sans clé).
- 📱 **Navigation en bas** — barre d'onglets fixe (Accueil · Courses · + · Clients · Plus).
- 👤 **Clients habitués** — base recherchable, retrouvés à la création d'une course.
- 📆 **Export calendrier natif** — bouton « Agenda » : `.ics` sur iPhone, lien
  Google Agenda sur Android. **Titre + notes personnalisables** avec des
  placeholders (super-admin).
- 📊 **Mes statistiques** — vue unique par conducteur, consultée par le
  super-admin via « voir en tant que » (impersonation).
- 🔐 **Authentification** — Cloudflare Zero Trust (e-mail Google + JWT) et login
  local par mot de passe en LAN. Cycle de vie des comptes, rôles, audit.
- 📱 **PWA** — installable sur l'écran d'accueil iOS / Android (manifest + service worker).

---

## Installation en local (développement / test)

Prérequis : **Python 3.10+**.

```bash
git clone https://github.com/SuperNon0/VTC.git
cd VTC

python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Édite .env : mets au minimum
#   SECRET_KEY=...            (python -c "import secrets; print(secrets.token_hex(32))")
#   SUPERADMIN_PASSWORD=...   (mot de passe de connexion locale)
#   CF_VERIFY_JWT=false       (pas de Cloudflare en local)
#   ALLOW_LOCAL_LOGIN=true

python run.py                 # → http://127.0.0.1:8000
```

Connecte-toi avec le `SUPERADMIN_PASSWORD` choisi. Tu es super-admin **et**
conducteur.

---

## Installation en production (Proxmox + Cloudflare)

**Option 1 — installateur 1 commande** (à lancer sur le shell du nœud Proxmox) :

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/VTC/main/install.sh)"
```

Crée un conteneur LXC Debian, installe l'app dans `/opt/vtc`, génère le `.env`,
crée le service systemd `vtc` et un helper de mise à jour. Options :
`CTID=130 ADMIN_PASSWORD=... ADMIN_EMAIL=ton@gmail.com bash -c "$(curl ...)"`.

> 💡 En passant **`ADMIN_EMAIL=ton@gmail.com`** dès l'installation, ton unique
> compte super-admin est créé **directement avec ton e-mail Google** (login
> mot de passe **et** Cloudflare) — aucun réglage à faire ensuite.

**Option 2 — sur une machine/CT déjà prête** :

```bash
sudo bash /opt/vtc/deploy/install_lxc.sh   # venv + service systemd
# renseigne /opt/vtc/.env, puis :
sudo systemctl start vtc
journalctl -u vtc -f
```

Puis expose l'app derrière un **tunnel Cloudflare** et active la vérification du
JWT (`CF_VERIFY_JWT=true`, `SESSION_COOKIE_SECURE=true`). Détail complet :
[`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md) et
[`docs/tuto-cloudflare-sso.md`](docs/tuto-cloudflare-sso.md).

> ⚠️ En production, l'origine doit être **injoignable sans passer par
> Cloudflare** (tunnel + pare-feu), et `CF_VERIFY_JWT=true`. Voir §9 de la spec d'auth.

---

## Première configuration (super-admin)

Une fois connecté en super-admin, ouvre **Paramètres** :

1. **Extraction IA** — choisis Gemini / Mistral / Groq et colle ta **clé API**
   (gratuite : Google AI Studio, console.mistral.ai ou console.groq.com).
2. **Grilles tarifaires** — ajoute tes trajets fréquents et leur prix.
3. **Lieux fréquents** — ajoute gares / aéroports / points habituels (tous les
   conducteurs peuvent aussi compléter cette liste ensuite).
4. **Modèle calendrier** — personnalise le titre et les notes des événements
   exportés (voir ci-dessous).
5. **Cloudflare / Accès** — équipe + AUD si tu connectes des conducteurs par
   e-mail Google. **Comptes** — valide les demandes d'accès des conducteurs.

### Personnaliser l'export calendrier (placeholders)

Dans *Paramètres → Modèle calendrier*, le **titre** et les **notes** de
l'événement se composent avec des **placeholders** entre crochets, remplacés par
les infos de la course. Exemple : `Prix : [prix]` devient `Prix : 32.00 €`.

Placeholders disponibles : `[nom]`, `[telephone]`, `[depart]`, `[arrivee]`,
`[prix]`, `[date]`, `[statut]`, `[habitue]` (« Habitué » ou « Nouveau client »),
`[notes]`.

Valeurs par défaut :

- **Titre** : `[nom] · [depart] → [arrivee]`
- **Notes** : nom (+ habitué), téléphone, départ, arrivée, prix, date, notes.

Clique un placeholder pour l'insérer, vérifie l'**aperçu en direct**, puis
*Enregistrer*. *Réinitialiser* rétablit les valeurs par défaut.

---

## Rôles et permissions

| Action | Conducteur (`membre`) | Super-admin |
|---|:---:|:---:|
| Voir son calendrier, créer/assigner une course, changer un statut | ✅ | ✅ |
| Ajouter/supprimer un **client** habitué | ✅ | ✅ |
| Ajouter/supprimer un **lieu** fréquent | ✅ | ✅ |
| Ses **statistiques** personnelles | ✅ | ✅ |
| **Grilles tarifaires** | ❌ | ✅ |
| **Extraction IA** (fournisseur + clé) | ❌ | ✅ |
| **Modèle d'export calendrier** | ❌ | ✅ |
| **Estimation de trajet** (activer/désactiver) | ❌ | ✅ |
| **Comptes** (valider, bloquer, « voir en tant que ») | ❌ | ✅ |
| **Mise à jour** du site, réglages Cloudflare | ❌ | ✅ |

---

## Mise à jour du site

Réservée au super-admin. Deux façons :

- **Depuis l'app** : *Paramètres → Mise à jour → ↻ Mettre à jour* (git pull +
  dépendances + rechargement).
- **En ligne de commande** : `sudo bash /opt/vtc/deploy/update.sh`.

---

## Mot de passe oublié

Le mot de passe super-admin se réinitialise **sur le serveur** (accès shell) :

```bash
sudo bash /opt/vtc/deploy/reset_admin.sh              # génère un nouveau mot de passe
sudo bash /opt/vtc/deploy/reset_admin.sh "MonMotDePasse"
```

## Vérifier le fuseau horaire du serveur

Les horaires des courses utilisent l'heure **locale du serveur**. Pour vérifier
(et corriger si besoin) :

```bash
sudo bash /opt/vtc/deploy/check_timezone.sh          # affiche le fuseau + l'heure vue par l'app
sudo timedatectl set-timezone Europe/Paris           # corriger (France)
sudo systemctl restart vtc
```

## Unifier ton compte (mot de passe + e-mail Google)

Pour n'avoir **qu'un seul compte super-admin** accessible par mot de passe **et**
par ton e-mail Google (Cloudflare). Depuis l'app : *Plus → Paramètres → Mon
e-mail Google*. En ligne de commande (fusionne aussi un éventuel doublon de
compte, sans perdre de course) :

```bash
sudo bash /opt/vtc/deploy/set_email.sh ton.email@gmail.com   # rattacher
sudo bash /opt/vtc/deploy/set_email.sh --clear               # détacher
```

---

## Documentation détaillée

- [`docs/taxi-vtc.md`](docs/taxi-vtc.md) — **fonctionnalités métier** (modèle de données, IA, push, calendrier…).
- [`CLAUDE.md`](CLAUDE.md) — contrat de reproduction + décisions structurantes.
- [`docs/authentification-v2.md`](docs/authentification-v2.md) — spec de l'auth.
- [`docs/theme-recipelog.md`](docs/theme-recipelog.md) — cahier du thème.
- [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md) — BotPanel (cycle de vie des comptes).
- [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md) — Proxmox + Cloudflare.

## Stack

Flask 3 · SQLite · gunicorn · PyJWT · pywebpush · Jinja2 · CSS pur (thème RecipeLog).

Ne modifie pas le thème ni la sécurité de l'auth sans raison — voir `CLAUDE.md`.
