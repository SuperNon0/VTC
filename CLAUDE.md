# CLAUDE.md — instructions pour le développeur (IA)

> Ce fichier est lu en premier par l'assistant qui reprend ce dépôt. Il fixe le
> **contrat** : ce qui doit être reproduit **à l'identique**, et ce qui est libre.

## 1. Ce qu'est ce dépôt

**VTC** — application web (PWA) de gestion d'une activité taxi/VTC pour une
équipe (un super-admin qui est aussi conducteur, et plusieurs conducteurs).
Construite sur le template de fondation `SuperNon0/site` (thème RecipeLog + auth
Cloudflare Zero Trust). Le cahier des charges métier fait foi ; l'implémentation
métier est décrite dans [`docs/taxi-vtc.md`](docs/taxi-vtc.md).

Le socle repris du template, à conserver :

1. **Le thème visuel « RecipeLog »** (dark + accent doré) — voir
   [`docs/theme-recipelog.md`](docs/theme-recipelog.md), implémenté dans
   [`panel/static/style.css`](panel/static/style.css) + [`fonts.css`](panel/static/fonts.css).
2. **L'authentification v2 multi-comptes** derrière **Cloudflare Zero Trust** —
   spec [`docs/authentification-v2.md`](docs/authentification-v2.md), maquettes de
   référence [`docs/maquettes-auth-v2/`](docs/maquettes-auth-v2/).
3. **Les notifications via BotPanel** (cycle de vie des comptes uniquement) —
   [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md),
   helper [`panel/notify.py`](panel/notify.py). ⚠️ Les notifications **métier**
   des conducteurs passent par **Web Push** (`panel/webpush.py`), indépendamment
   de BotPanel (cahier §8).
4. **Le déploiement Proxmox (LXC/VM) + Cloudflare** —
   [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md).

Ajouté par le projet VTC (voir [`docs/taxi-vtc.md`](docs/taxi-vtc.md)) :
courses (créateur ≠ conducteur assigné), calendrier personnel, extraction IA
configurable des infos client, grilles tarifaires, lieux fréquents, clients
habitués, Web Push, PWA (manifest + service worker), export calendrier natif.

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

## 3. Décisions structurantes déjà prises (VTC)

- **Marque** via `.env` : `BRAND_PREFIX=V`, `BRAND_SUFFIX=TC`, `BRAND_BADGE`.
- **Cloisonnement (auth-v2 §7)** : les **courses** sont une table **partagée**
  avec propriété par ligne. Chaque course distingue `createur_id` (qui l'a
  saisie) et `conducteur_id` (à qui elle est confiée). Toute la logique
  d'affichage/notif/stats se base sur le **conducteur assigné**, jamais sur le
  créateur (cahier §5). Le créateur a une vue séparée « Mes courses ».
- **Extensibilité prévue** (à ne PAS développer maintenant, mais gardée facile) :
  - prix par distance (§6.3) → colonne `courses.distance_km` + `prix_source`
    déjà en place ; ajouter un mode `'distance'` sans toucher au reste.
  - statistiques (§6.7) → colonnes date/prix/statut/conducteur indexées ;
    la vue `/mes-stats` est **unique** et réutilisée par le super-admin via
    « voir en tant que » (ne pas créer d'écran stats séparé).

## 4. Rôles (VTC)

Deux rôles, conformes au template : `super_admin` et `membre` (= **conducteur**
dans toute la logique métier). Le `super_admin` **est aussi conducteur** : il a
son propre calendrier et ses stats, exactement comme un `membre`. N'importe quel
conducteur (super-admin inclus) peut créer une course et l'assigner à n'importe
qui — pas de rôle « dispatcher » séparé (cahier §3). Ne pas réintroduire le rôle
`admin` intermédiaire.

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
  config.py           config depuis .env (marque VTC)
  db.py               SQLite : comptes + audit + app_settings + modèle métier
                      (courses, clients, tarifs, lieux, push_subscriptions)
  auth.py             Cloudflare Access (JWT), session, décorateurs
  notify.py           helper BotPanel (cycle de vie des comptes UNIQUEMENT)
  courses.py          accès données métier : courses/clients/tarifs/lieux
  ai.py               extraction IA configurable (Gemini/Mistral/Groq via REST)
  webpush.py          Web Push : clés VAPID, souscriptions, envoi
  settings.py         réglages en base (Cloudflare, IA, VAPID…)
  utils.py            format date FR + export calendrier (.ics / Google Agenda)
  routes/
    auth_routes.py    gateway, login local, demande d'accès, logout
    accounts_routes.py gestion comptes + impersonation + Paramètres/mdp/Cloudflare
    config_routes.py  Paramètres taxi : IA, tarifs, lieux, modèle calendrier ; clients
    main.py           calendrier, création de course, mes courses, stats, push, ICS
  templates/          base + auth + parametres + dashboard(calendrier) +
                      nouvelle_course + mes_courses + mes_stats + clients +
                      config_ia/tarifs/lieux/calendrier
  static/             style.css (thème + section taxi), fonts.css, logo.svg,
                      manifest.json (PWA), sw.js (service worker + push)
docs/                 spec auth, thème, notifications, déploiement, maquettes,
                      taxi-vtc.md (features métier)
deploy/               install_lxc.sh, site-base.service, update.sh
run.py / wsgi.py      entrées dev / prod (gunicorn)
```

## 7. Vérifier avant de livrer

- [ ] Le rendu des écrans d'auth correspond aux captures de référence.
- [ ] Login local (LAN) ET parcours Cloudflare (demande→attente→validation) OK.
- [ ] `/api/*` renvoie `Cache-Control: no-store`.
- [ ] `CF_VERIFY_JWT=true` et `SESSION_COOKIE_SECURE=true` en production.
- [ ] Notifications BotPanel branchées sur les bons slugs.
