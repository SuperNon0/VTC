# CLAUDE.md — instructions pour le développeur (IA)

> Ce fichier est lu en premier par l'assistant qui reprend ce dépôt. Il fixe le
> **contrat** : ce qui doit être reproduit **à l'identique**, et ce qui est libre.

## 1. Ce qu'est ce dépôt

Un **site de base** (template de fondation) réutilisé pour démarrer chaque
nouveau projet. Il fournit, prêts à l'emploi :

1. **Le thème visuel « RecipeLog »** (dark + accent doré) — voir
   [`docs/theme-recipelog.md`](docs/theme-recipelog.md), implémenté dans
   [`panel/static/style.css`](panel/static/style.css) + [`fonts.css`](panel/static/fonts.css).
2. **L'authentification v2 multi-comptes** derrière **Cloudflare Zero Trust** —
   spec [`docs/authentification-v2.md`](docs/authentification-v2.md), maquettes de
   référence [`docs/maquettes-auth-v2/`](docs/maquettes-auth-v2/).
3. **Les notifications via BotPanel** — [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md),
   helper [`panel/notify.py`](panel/notify.py).
4. **Le déploiement Proxmox (LXC/VM) + Cloudflare** —
   [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md).

## 2. Règles de reproduction (NE PAS DÉVIER)

- **Le thème est un contrat visuel.** Les couleurs, polices, rayons et classes de
  `panel/static/style.css` doivent rester **identiques**. Le rendu doit
  correspondre aux captures de `docs/maquettes-auth-v2/captures/`. N'invente pas
  de nouvelles couleurs : passe **toujours** par les variables `:root`.
- **Les écrans d'auth** (`login`, `demande`, `attente`, `refus`, `bloque`,
  `comptes`, bandeau d'impersonation) doivent rester **fidèles aux maquettes**
  (structure HTML + classes). Les templates correspondants sont dans
  `panel/templates/`.
- **La sécurité de l'auth** (vérification du JWT Cloudflare + `aud`, dernier
  super-admin indestructible, sessions `compte_id`+`role`, `/api/*` en
  `no-store`, anti-force-brute) ne doit pas être affaiblie (spec §9).
- **Les notifications passent par BotPanel** (`panel/notify.py`), jamais en
  appelant Discord directement.

## 3. Ce que TU personnalises pour un projet

- **La marque** via `.env` : `BRAND_PREFIX`, `BRAND_SUFFIX`, `BRAND_BADGE`, et le
  logo `panel/static/logo.svg` (garde le viewBox 44×44).
- **Le contenu applicatif** : remplace `panel/templates/dashboard.html` et
  `panel/routes/main.py` par les écrans de ton projet, en réutilisant les classes
  du thème (`fl-card`, `fl-title-serif`, `.btn`, etc.).
- **Le modèle de données métier** : ajoute tes tables. ⚠️ **Décision bloquante**
  avant de coder du contenu multi-utilisateurs : bibliothèque **partagée** ou
  **cloisonnée** par compte ? Voir `authentification-v2.md` §7. À **poser au
  propriétaire du projet**.

## 4. Rôles (ce template)

Deux rôles seulement : `super_admin` (toi — gère tout, login local) et `membre`.
Le rôle `admin` intermédiaire de la spec n'est **pas** activé ici (simplification
assumée). Ne le réintroduis que si le propriétaire le demande explicitement.

## 5. Lancer en local

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis renseigne SECRET_KEY + SUPERADMIN_PASSWORD
python run.py               # http://127.0.0.1:8000
```

En dev sans Cloudflare : `CF_VERIFY_JWT=false` + `ALLOW_LOCAL_LOGIN=true`, et
connecte-toi en local avec `SUPERADMIN_PASSWORD`.

## 6. Structure

```
panel/
  __init__.py         app factory (blueprints, contexte, no-store)
  config.py           config depuis .env
  db.py               SQLite : schéma `comptes` + `audit`, amorce super-admin
  auth.py             Cloudflare Access (JWT), session, décorateurs
  notify.py           helper BotPanel notify(slug, **vars)
  reset_admin.py      CLI de réinitialisation du mdp super-admin (python -m panel.reset_admin)
  utils.py            format date FR
  routes/
    auth_routes.py    gateway, login local, demande d'accès, mot de passe oublié, logout
    accounts_routes.py gestion comptes + impersonation + Paramètres/mdp (spec §5/§6/§8)
    main.py           écran applicatif (à remplacer)
  templates/          base + écrans d'auth + parametres + oubli + dashboard
  static/             style.css (thème), fonts.css, logo.svg
docs/                 spec auth, thème, notifications, déploiement, maquettes
deploy/               install_lxc.sh, site-base.service, update.sh
run.py / wsgi.py      entrées dev / prod (gunicorn)
```

## 7. Vérifier avant de livrer

- [ ] Le rendu des écrans d'auth correspond aux captures de référence.
- [ ] Login local (LAN) ET parcours Cloudflare (demande→attente→validation) OK.
- [ ] `/api/*` renvoie `Cache-Control: no-store`.
- [ ] `CF_VERIFY_JWT=true` et `SESSION_COOKIE_SECURE=true` en production.
- [ ] Notifications BotPanel branchées sur les bons slugs.
