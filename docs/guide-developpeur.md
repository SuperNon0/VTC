# Guide du développeur — comprendre et étendre le site de base

Ce guide explique **comment le code fonctionne** et **pourquoi** il est fait ainsi,
pour qu'un développeur (humain ou IA) qui reprend ce dépôt puisse construire un
vrai projet dessus **sans casser le socle**. Il complète :

- [`CLAUDE.md`](../CLAUDE.md) — le **contrat** (ce qui est figé vs personnalisable) ;
- [`authentification-v2.md`](authentification-v2.md) — la spec fonctionnelle de l'auth ;
- [`theme-recipelog.md`](theme-recipelog.md) — le cahier des charges du thème ;
- [`notifications-botpanel.md`](notifications-botpanel.md), [`deploiement-proxmox.md`](deploiement-proxmox.md),
  [`versions.md`](versions.md), [`mobile-anti-zoom.md`](mobile-anti-zoom.md).

> **Philosophie.** Le socle (thème + auth + notifications + déploiement) se
> **reproduit à l'identique**. Ton travail de projet, c'est le **contenu métier**
> (écrans + tables), branché sur ce socle. Ne réécris pas l'auth ou le thème :
> réutilise-les.

---

## 1. Vue d'ensemble

Application **Flask** (Python) servie par **gunicorn** en production, données en
**SQLite**. Pas de framework front : des templates **Jinja2** + un **CSS pur**
(le thème). Pourquoi ce choix ? Parce que l'authentification derrière Cloudflare
Access repose sur des **en-têtes de requête** et des **sessions serveur** : il
faut un backend. Le thème, lui, est du CSS portable (aucune dépendance à un
framework front).

```
Navigateur
   │  (derrière Cloudflare Access en prod : en-têtes Cf-Access-*)
   ▼
gunicorn ──► panel/__init__.py  (app factory)
                │  enregistre les blueprints + context processors + no-store
                ├─ routes/auth_routes.py     parcours de connexion
                ├─ routes/accounts_routes.py gestion comptes + Paramètres + impersonation
                ├─ routes/system_routes.py   /api/system/* (mise à jour)
                └─ routes/main.py            écran applicatif (à remplacer)
                        │
                        ├─ auth.py     Cloudflare Access (JWT) + session + décorateurs
                        ├─ db.py       SQLite : comptes + audit
                        ├─ notify.py   BotPanel notify(slug, **vars)
                        └─ templates/ + static/  (thème)
```

### Les deux couches de sécurité (à toujours garder en tête)

| Couche | Décide… | Comment |
|---|---|---|
| **Cloudflare Access** | *qui peut atteindre le site* | e-mail Google autorisé (policy) |
| **L'application** | *ce qui se passe une fois entré* | rôles, états de compte, impersonation |

Cloudflare ne sait faire que « autorisé / refusé ». **Tout le reste** (rôles,
cycle de vie, cloisonnement) est géré par l'app. C'est la règle d'or de la spec.

---

## 2. Le cœur : `panel/__init__.py` (app factory)

`create_app()` assemble tout :

1. charge la config (`config.py`) ;
2. branche la fermeture de la connexion SQLite en fin de requête ;
3. **initialise la base** (`init_db()`) — schéma + amorce du super-admin ;
4. enregistre les **blueprints** (groupes de routes) ;
5. déclare deux comportements transverses :
   - un **context processor** qui injecte dans *tous* les templates la marque
     (`brand`) et l'objet `impersonation` (pour le bandeau) — évite de le passer
     à la main dans chaque `render_template` ;
   - un **`after_request`** qui met `Cache-Control: no-store` sur **toutes** les
     routes `/api/*` (exigence de sécurité : ne pas mettre en cache des données
     sensibles).

> **Pourquoi une factory ?** Pour pouvoir créer l'app avec une config de test
> (voir les tests), et pour un démarrage propre sous gunicorn (`wsgi.py`).

---

## 3. Configuration : `panel/config.py`

Tout vient de l'environnement (`.env`), **rien n'est en dur**. Variables clés :

| Variable | Rôle | Défaut |
|---|---|---|
| `SECRET_KEY` | signe les sessions | *dev* (à changer) |
| `SESSION_COOKIE_SECURE` | cookie HTTPS only | `false` (mettre `true` en prod) |
| `BRAND_PREFIX/SUFFIX/BADGE` | marque (logo + badge) | `site` / `base` / … |
| `DATABASE_PATH` | fichier SQLite | `./data/site-base.db` |
| `SUPERADMIN_PASSWORD` | mdp login local (amorce) | vide |
| `SUPERADMIN_EMAIL` | e-mail Google du super-admin | vide |
| `CF_ACCESS_TEAM_DOMAIN` | `<team>.cloudflareaccess.com` | vide |
| `CF_ACCESS_AUD` | AUD tag de l'app Access | vide |
| `CF_VERIFY_JWT` | vérifier le JWT Cloudflare | `true` |
| `ALLOW_LOCAL_LOGIN` | login local par mdp (LAN) | `true` |
| `BOTPANEL_URL` | adresse BotPanel (vide = notifs off) | vide |
| `NOTIFY_SLUG_*` | slugs des notifications | `acces_*` |

`load_dotenv()` charge `.env` automatiquement au démarrage.

---

## 4. Données : `panel/db.py`

Deux tables seulement dans le socle :

- **`comptes`** — le cœur de l'auth (voir spec §7) : `email`, `role`
  (`super_admin`|`membre`), `etat` (`pending`|`actif`|`refused`|`bloque`),
  `mdp_hash` (seulement pour le login local), et des timestamps
  (`cree`, `valide`, `bloque`, `derniere_cnx`).
- **`audit`** — journal des actions sensibles (validation, blocage, suppression,
  impersonation, reset mdp…). **Pourquoi ?** L'impersonation et la gestion des
  comptes sont des pouvoirs sensibles : on trace *qui a fait quoi, quand*.

Fonctions importantes :
- `get_db()` — une connexion SQLite **par requête** (attachée à `g`), fermée
  automatiquement à la fin.
- `audit(action, acteur, cible, detail)` — écrit une ligne de journal.
- `init_db()` — crée le schéma (idempotent) et **amorce le super-admin** depuis
  `SUPERADMIN_PASSWORD`/`SUPERADMIN_EMAIL` s'il n'en existe aucun.

> **Le contenu métier n'est PAS ici.** Tu ajouteras tes tables (films, recettes,
> etc.) dans ton projet. Voir §10 (partagé vs cloisonné).

---

## 5. Authentification : `panel/auth.py`

C'est le fichier le plus sensible. Il fait trois choses.

### a) Lire l'e-mail Cloudflare de façon sûre — `cf_access_email()`

- En prod (`CF_VERIFY_JWT=true`, défaut) : on **vérifie le JWT**
  `Cf-Access-Jwt-Assertion` contre les clés publiques de ton équipe Cloudflare
  (via `PyJWKClient`) **et** on contrôle l'`aud` et l'`iss`. On renvoie l'e-mail
  *contenu dans le token vérifié*.
- **Pourquoi c'est crucial :** l'en-tête `Cf-Access-Authenticated-User-Email` est
  facile à **forger** si quelqu'un atteint l'origine sans passer par Cloudflare.
  Sans vérif JWT, il pourrait se faire passer pour n'importe qui. On ne fait donc
  **jamais** confiance à l'en-tête seul en prod.
- En dev (`CF_VERIFY_JWT=false`) : on se contente de l'en-tête (pratique pour
  tester en local, jamais en prod exposé).

### b) Modéliser la session

Une session porte `compte_id` + `role` (+ `impersonator_id` si impersonation) —
**pas** un simple booléen `logged_in`. `current_compte()` renvoie le compte
**effectif** (celui impersonné le cas échéant). `is_super_admin()` regarde le
**vrai** acteur (l'impersonateur s'il y en a un).

### c) Protéger les routes — décorateurs

- `@login_required` — exige un compte **actif**, sinon renvoie vers `gateway`.
- `@super_admin_required` — exige que le vrai acteur soit `super_admin`.

---

## 6. Parcours de connexion : `panel/routes/auth_routes.py`

Le point d'entrée est **`gateway()`**, qui implémente l'arbre de décision de la
spec §4 :

```
cf_access_email() ?
   ├─ None (accès LAN)        → login.html (mot de passe super-admin)
   └─ e-mail vérifié :
        compte inexistant     → demande.html   (« Demander un accès »)
        etat == pending       → attente.html
        etat == refused       → refus.html
        etat == bloque        → bloque.html
        etat == actif         → login_compte() puis dashboard
```

Autres routes :
- `login` (POST) — login local par mot de passe : `time.sleep(1)` (anti-force
  brute), compare au `mdp_hash` du super-admin. Ignoré si un e-mail Cloudflare
  est présent (on ne mélange pas les deux canaux).
- `request_access` (POST) — crée un compte `pending` (ou `refused → pending` pour
  « Redemander »), journalise et **notifie BotPanel**.
- `forgot` (GET) — page expliquant la commande de réinitialisation (le reset se
  fait côté serveur, cf. §9).
- `logout` — vide la session.

---

## 7. Gestion des comptes & impersonation : `panel/routes/accounts_routes.py`

Toutes ces routes sont `@super_admin_required` et en `/api/*` (donc `no-store`).

- `comptes` (GET `/parametres/comptes`) — l'écran de gestion (maquette 6) :
  demandes en attente + membres. On convertit les lignes SQLite en dicts avec des
  dates formatées FR (`_row_to_view`).
- `valider` / `refuser` / `bloquer` / `debloquer` / `supprimer` — transitions
  d'état. Chacune **journalise** (`audit`) et, quand c'est pertinent, **notifie**
  (validation, blocage). Le **dernier super-admin est indestructible**
  (`supprimer` refuse un `super_admin`).
- **Impersonation** (`impersonate` / `impersonate_stop`) — « voir en tant que » :
  - `impersonate` met `session['impersonator_id'] = <toi>` puis
    `session['compte_id'] = <cible>`. À partir de là, `current_compte()` renvoie
    la **cible** → tu vois/édites *ses* données ; `is_super_admin()` reste vrai
    (il regarde l'impersonateur).
  - Garde-fous : pas d'impersonation en cascade, ni d'un autre super-admin.
  - Le **bandeau** permanent est rendu par `base.html` grâce à l'objet
    `impersonation` injecté par le context processor.
  - `impersonate_stop` restaure `compte_id = impersonator_id`.

**Paramètres & mot de passe** (mêmes fichier) :
- `parametres` (GET) — page Paramètres (mot de passe + comptes + mise à jour).
- `changer_mdp` (POST) — change le mot de passe du super-admin (vérifie l'actuel ;
  **bloqué pendant une impersonation** — on ne change pas le mdp de quelqu'un
  d'autre).

---

## 8. Mises à jour : `panel/routes/system_routes.py`

Le bouton **Paramètres → Mise à jour** appelle ces endpoints (super-admin,
`no-store`, bloqués en impersonation) :

- `GET /api/system/info` — version courante (`git describe`), branche, état du
  service systemd.
- `POST /api/system/update` — `git fetch --tags` puis **checkout de la dernière
  version** (tag `vX.Y.Z`, ou repli sur la branche si aucun tag) ; `pip install`.
  Rollback possible : `{"ref": "v1.0.0"}`.
- `POST /api/system/restart` — `sudo systemctl restart site-base` (autorisé par
  une règle sudoers **strictement limitée**, posée par `install_lxc.sh`).

**Pourquoi des tags et pas une branche ?** Pour raisonner en **versions**
(`v1.0.0`, `v1.1.0`…) plutôt qu'en noms de branches. Détails : `versions.md`.

---

## 9. Notifications : `panel/notify.py`

Un seul helper : `notify(slug, **vars)`. Il poste `{"id": slug, "vars": {...}}`
sur `{BOTPANEL_URL}/api/notify`. **Propriétés voulues :**
- si `BOTPANEL_URL` est vide → **no-op** (les notifs sont désactivées, l'app
  marche quand même) ;
- **n'échoue jamais** — une notif injoignable est seulement journalisée, elle ne
  casse pas la requête métier.

Le contenu de la notif (titre, message, couleur, boutons…) est défini **côté
BotPanel** et repéré par son *slug*. Le site n'envoie que le slug + des variables.

### Réinitialisation du mot de passe : `panel/reset_admin.py`

CLI (`python -m panel.reset_admin`) qui réécrit le `mdp_hash` du super-admin —
utile en cas d'oubli, s'exécute **sur le serveur** (accès shell), donc sans être
connecté. Wrappé par `deploy/reset_admin.sh` en déploiement.

---

## 10. Recettes — étendre le socle

### Ajouter un écran métier

1. Crée un template qui `{% extends "base.html" %}` et remplis `{% block content %}`.
2. Réutilise les classes du thème (`fl-card`, `fl-title-serif`, `.btn`, …) — voir
   `theme-recipelog.md`. **N'invente pas de couleurs**, passe par les variables `:root`.
3. Ajoute une route dans un blueprint (ou remplace `routes/main.py`), protégée par
   `@login_required`.

### Ajouter une table métier — ⚠️ décision bloquante d'abord

Avant de coder du contenu multi-utilisateurs, **tranche avec le propriétaire** :
bibliothèque **partagée** (tout le monde voit la même) ou **cloisonnée** (chacun
la sienne) ? Voir `authentification-v2.md` §7. Ça conditionne tout le reste :
- **Partagée** : tes tables n'ont pas besoin de `compte_id`. Léger.
- **Cloisonnée** : ajoute `compte_id` (le compte *effectif*, cf. impersonation) et
  filtre **chaque** requête par ce compte. Lourd mais fait proprement avec une
  fonction utilitaire centrale.

### Ajouter une notification

1. Crée la notif dans BotPanel, note son slug.
2. Appelle `notify("ton_slug", cle="valeur")` là où l'événement se produit.
3. (Optionnel) expose le slug en config si tu veux le rendre paramétrable.

### Personnaliser la marque

`.env` : `BRAND_PREFIX`, `BRAND_SUFFIX`, `BRAND_BADGE`. Remplace
`panel/static/logo.svg` (garde le viewBox 44×44).

---

## 11. Ce qu'il ne faut PAS affaiblir (sécurité)

1. **Vérif JWT Cloudflare + `aud`** en prod (`CF_VERIFY_JWT=true`).
2. **`/api/*` en `no-store`** (déjà global dans `__init__.py`).
3. **Dernier super-admin indestructible** (pas de suppression/rétrogradation).
4. **Session = `compte_id` + `role`** (+ `impersonator_id`), jamais un simple flag.
5. **Anti-force brute** sur le login local (`time.sleep(1)`).
6. **Journal d'audit** sur les actions sensibles.
7. **Origine injoignable sans Cloudflare** en prod (tunnel `cloudflared`).

---

## 12. Lancer & tester en local

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # renseigne SECRET_KEY + SUPERADMIN_PASSWORD
python run.py             # http://127.0.0.1:8000
```

En dev sans Cloudflare : `CF_VERIFY_JWT=false` + `ALLOW_LOCAL_LOGIN=true`, puis
connecte-toi en local avec `SUPERADMIN_PASSWORD`. Vérifie le parcours complet :
login local → Paramètres → Comptes, puis (en simulant l'en-tête Cloudflare)
demande → attente → validation.

---

## 13. Carte du dépôt (rappel)

| Chemin | Rôle |
|---|---|
| `panel/__init__.py` | app factory (blueprints, contexte, no-store) |
| `panel/config.py` | config depuis `.env` |
| `panel/db.py` | SQLite : `comptes` + `audit`, amorce super-admin |
| `panel/auth.py` | Cloudflare Access (JWT), session, décorateurs |
| `panel/notify.py` | helper BotPanel |
| `panel/reset_admin.py` | CLI reset mdp super-admin |
| `panel/routes/*` | auth / comptes+paramètres / système / applicatif |
| `panel/templates/*` | base + écrans d'auth + paramètres + dashboard |
| `panel/static/*` | `style.css` (thème), `fonts.css`, `logo.svg` |
| `docs/*` | specs, thème, notifications, déploiement, versions, ce guide |
| `deploy/*` | `install_lxc.sh`, `site-base.service`, `update.sh`, `reset_admin.sh` |
| `run.py` / `wsgi.py` | entrées dev / prod |
