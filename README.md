<div align="center">

# site-base — modèle en couches

**Fondation réutilisable pour démarrer un projet web.** Thème « RecipeLog »
(dark + doré), authentification multi-comptes derrière **Cloudflare Zero Trust**,
notifications **BotPanel**, et un **socle verrouillé qui se met à jour tout seul**.

</div>

---

> ## 🟡 À LIRE EN PREMIER (dev IA)
>
> Ce dépôt a **deux couches** :
> - **`base/`** = la fondation (login, thème, permissions, page Paramètres, mises
>   à jour). **Tu n'y touches JAMAIS.** Elle se met à jour toute seule.
> - **`app/`** = **ton projet** (tes écrans, tes tables, tes réglages). **Tout ton
>   travail vit ici.** Modèle de départ prêt : **`app.example/`** → copie-le en `app/`.
>
> **Les 3 règles d'or :**
> 1. **Ne modifie jamais `base/`.** (Un verrou CI + pre-commit le refuse — voir plus bas.)
> 2. **Développe le métier sur sa propre branche**, jamais mélangée avec la base.
> 3. Si tu crois qu'il faut changer `base/` → **arrête-toi et demande au propriétaire.**
>
> Contrat complet : [`CLAUDE.md`](CLAUDE.md) · Modèle détaillé : [`docs/modele-couches.md`](docs/modele-couches.md)

---

## Ce que tu obtiens gratuitement (dans `base/`, sans rien coder)

- 🎨 **Thème RecipeLog** — dark, accent doré `#e8c547`, DM Serif Display + DM Mono.
  Réutilise ses classes (`fl-card`, `fl-title-serif`, `.btn`…) via `{% extends "base.html" %}`.
- 🔐 **Auth v2 multi-comptes** — cycle `pending → actif / refused / bloqué`, rôles
  `super_admin` / `membre`, « voir en tant que » (impersonation) + bandeau, audit.
- ☁️ **Cloudflare Zero Trust** — e-mail vérifié par **JWT** (`RS256` + `aud` + `iss`),
  login local par mot de passe en LAN. Réglable dans l'UI (Paramètres → Cloudflare / Accès).
- 🔔 **Notifications BotPanel** — helper `notify(slug, **vars)` déjà branché sur le
  cycle de vie des comptes.
- 🧩 **Permissions par site** — gestion des comptes, profils, mot de passe, mises à
  jour, chacune `off` / `membre` / `super_admin` (`python manage.py setup`).
- 🔄 **Deux mises à jour, deux pages** — voir plus bas.
- 🔒 **Base verrouillée** — CI + pre-commit refusent toute modif de `base/` dans un projet.

---

## Démarrage (dev local, sans Cloudflare)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Dans `.env`, mets au minimum :

```env
SECRET_KEY=une-longue-chaine-aleatoire
SUPERADMIN_PASSWORD=tonMotDePasse       # login LAN
CF_VERIFY_JWT=false                       # dev sans Cloudflare
ALLOW_LOCAL_LOGIN=true
```

Puis :

```bash
python run.py            # → http://127.0.0.1:8000  (login avec SUPERADMIN_PASSWORD)
```

`run.py` assemble tout seul `base/` + `app/` (rien à configurer côté chemins).
Sans dossier `app/`, la base tourne seule (écran de démo).

---

## Ajouter ton métier (le workflow)

```bash
python bootstrap_base.py       # récupère base/ (fondation) depuis site-base
cp -r app.example app          # démarre ton projet (la SEULE chose versionnée)
echo "base/" >> .gitignore     # base/ n'est jamais committée dans un projet
python run.py                  # l'accueil devient celui de app/
```

> **`base/` n'est pas versionnée dans un projet** : elle est fournie par
> `bootstrap_base.py` (installation) et par « Mettre à jour la base » (`sync_base`).
> Le dev ne peut donc rien pousser qui concerne la base. Prompt prêt à donner à un
> dev IA : [`docs/prompt-migration.md`](docs/prompt-migration.md).

Tu édites **uniquement** `app/` :

| Fichier | Rôle |
|---|---|
| `app/__init__.py` | `register(flask_app)` : branche tes blueprints. Déclare tes réglages via `flask_app.config["APP_REGLAGES_TEMPLATE"] = "app_reglages.html"`. |
| `app/routes.py` | tes écrans. Réutilise la base : `from panel.auth import login_required, current_compte` ; `from panel.db import get_db`. |
| `app/templates/` | tes gabarits. `{% extends "base.html" %}` → thème + en-tête + bandeau d'impersonation gratuits. Priment sur ceux de la base. |
| `app/schema.sql` | tes tables métier (exécuté automatiquement au démarrage). |

### Points d'extension fournis par la base

| Prise | Ce que tu fournis |
|---|---|
| **Écrans** | `register(flask_app)` enregistre tes blueprints (dont l'accueil `/`). |
| **Templates** | `app/templates/` s'ajoute et **prime** sur ceux de la base. |
| **Tables** | `app/schema.sql` est exécuté en plus du schéma de la base. |
| **Réglages** | `APP_REGLAGES_TEMPLATE` → la page **`/reglages`** de la base inclut ton partial (même thème, même cadre). Stocke tes options avec `panel.settings.set_setting` / `get_setting`. |

### Données par utilisateur (cloisonnées)

Nomme ta colonne **`compte_id`** et filtre par le compte **effectif** (impersonation
incluse) :

```python
cid = current_compte()["id"]
get_db().execute("SELECT * FROM films WHERE compte_id = ?", (cid,))
```

Bonus : la base sait réattribuer/fusionner ces lignes lors d'un changement d'e-mail
(`manage.py set_email`). Décision **partagé vs cloisonné** à poser au propriétaire.

---

## Deux pages, deux mises à jour (base vs application)

Tout est dessiné par la base → **identique sur tous tes sites** :

| | Page | Bouton de mise à jour | Verrouillé ? |
|---|---|---|---|
| **Site** (base) | `/parametres` | « Mettre à jour la base » (`sync_base`) | ✅ dans `base/` |
| **Application** (métier) | `/reglages` | « Mettre à jour l'application » (git du projet) | ❌ c'est ton `app/` |

Le **mécanisme** des deux boutons vit dans la base verrouillée (impossible à casser) ;
seule la **cible** change. La page `/reglages` appartient à la base (cadre + thème),
son **contenu** vient de ton partial `app_reglages.html`.

---

## Le verrou (pourquoi tu **ne peux pas** casser la base)

Deux garde-fous, en plus des règles d'or :

- **CI GitHub** — `.github/workflows/protect-base.yml` : tout push/PR modifiant
  `base/` dans un dépôt projet **échoue** (le dépôt site-base lui-même est exclu).
- **Hook pre-commit** — `.githooks/pre-commit` : bloque un commit local touchant
  `base/`. À activer une fois par projet :

  ```bash
  git config core.hooksPath .githooks
  ```

Rappel : `sync_base` **écrase** `base/` — toute modif locale y serait perdue.

---

## Commandes (`manage.py`)

```bash
python manage.py setup [--preset hub|perso]   # pose chaque permission, écrit .env
python manage.py reset_admin ["nouveau_mdp"]  # réinitialise le mot de passe admin
python manage.py set_email <email> | --clear  # rattache/fusionne l'e-mail admin
python manage.py sync_base [--ref 2.1.0]      # met à jour la couche base/
```

**Presets :** `hub` (données partagées : gestion des comptes on, impersonation off)
· `perso` (données cloisonnées : accès auto en actif, impersonation on).

## Tests

```bash
python tests/test_site.py     # batterie complète : 50 vérifs (base + surcouche)
```

Couvre auth, sécurité API (401 + `no-store`), cycle de vie des comptes, dernier
super-admin indestructible, impersonation, site perso, réglages, mises à jour,
et le branchement d'une surcouche `app/`. Aucune dépendance (pas besoin de pytest).

---

## Écrans d'auth (fournis par la base)

| Écran | Quand | Template |
|---|---|---|
| Login local | Accès LAN (mot de passe super-admin) | `login.html` |
| Demander un accès | E-mail CF autorisé mais inconnu (hub) | `demande.html` |
| En attente | Compte `pending` | `attente.html` |
| Refusé | Compte `refused` | `refus.html` |
| Suspendu | Compte `bloqué` | `bloque.html` |
| Comptes (gestion) | Super-admin (hub) | `comptes.html` |
| Paramètres du site | Admin | `parametres.html` |
| Réglages de l'app | Point d'extension surcouche | `reglages.html` (+ ton partial) |
| Mot de passe oublié | Depuis le login | `oubli.html` |

Maquettes de référence : [`docs/maquettes-auth-v2/`](docs/maquettes-auth-v2/). Ces
écrans sont un **contrat visuel** : ils vivent dans `base/`, tu n'y touches pas.

## Configuration `.env` (variables clés)

| Variable | Rôle |
|---|---|
| `SECRET_KEY` | signe les sessions (obligatoire). |
| `SUPERADMIN_PASSWORD` / `SUPERADMIN_EMAIL` | amorce le compte super-admin. |
| `CF_VERIFY_JWT` | `true` en prod (vérifie le JWT Cloudflare), `false` en dev LAN. |
| `ALLOW_LOCAL_LOGIN` | autorise le login par mot de passe (LAN). |
| `SESSION_COOKIE_SECURE` | `true` en prod (HTTPS). |
| `CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` | équipe + AUD Cloudflare (aussi réglables dans l'UI). |
| `BRAND_PREFIX` / `BRAND_SUFFIX` / `BRAND_BADGE` | ta marque. Logo : `base/panel/static/logo.svg`. |
| `CAP_*` | niveaux de permissions (ou `manage.py setup`). |
| `BOTPANEL_URL` | active les notifications (vide = désactivées). |

## Installation (Proxmox + Cloudflare)

`install.sh` détecte automatiquement **deux modes**.

**Option 1 — une commande, sur le shell du nœud Proxmox** (crée le conteneur LXC
Debian **et** installe VTC dedans, écoute sur l'IP du conteneur) :

```bash
ADMIN_EMAIL=toi@gmail.com \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/VTC/main/install.sh)"
```

> Options : `CTID=130 STORAGE=local-lvm BRIDGE=vmbr0 ADMIN_PASSWORD=… REPO_REF=… BIND=0.0.0.0:8000`.
> Tant que `main` ne porte pas encore le nouveau socle, ajoute
> `REPO_REF=claude/migration-nouveau-socle` (et vise ce chemin dans l'URL).
> En passant `ADMIN_EMAIL=` dès l'install, ton super-admin est créé d'emblée avec
> ton e-mail Google (login mot de passe **et** Cloudflare) — rien à régler ensuite.

**Option 2 — dans un conteneur / une VM déjà prête** (installe en place) :

```bash
sudo bash /opt/site-base/deploy/install_lxc.sh   # venv + amorçage base/ + service systemd
```

Détails : conteneur `site-base` sous `/opt/site-base`, service systemd
`site-base`, `base/` récupérée par `bootstrap_base.py` (jamais versionnée),
mise à jour sans sudo (SIGHUP gunicorn). Pour exposer publiquement, mets un
**tunnel Cloudflare** devant et passe `CF_VERIFY_JWT=true` +
`SESSION_COOKIE_SECURE=true`. Guide complet :
[`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md).

---

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — **contrat de reproduction** (à lire en premier).
- [`docs/modele-couches.md`](docs/modele-couches.md) — **base verrouillée + surcouche** (l'essentiel du dev IA).
- [`docs/prompt-migration.md`](docs/prompt-migration.md) — **prompt prêt à donner** à un dev IA pour migrer/démarrer un site.
- [`docs/guide-developpeur.md`](docs/guide-developpeur.md) — comprendre le code (architecture, pourquoi, recettes).
- [`docs/authentification-v2.md`](docs/authentification-v2.md) — spec complète de l'auth (sécurité §9).
- [`docs/theme-recipelog.md`](docs/theme-recipelog.md) — cahier des charges du thème.
- [`docs/permissions.md`](docs/permissions.md) — permissions par site (hub vs perso).
- [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md) — intégration BotPanel.
- [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md) — Proxmox + Cloudflare + mise à jour.
- [`docs/versions.md`](docs/versions.md) — versionnage (tags `vX.Y.Z`) & rollback.
- [`docs/mobile-anti-zoom.md`](docs/mobile-anti-zoom.md) — comportement « app native » mobile.
- [`CHANGELOG.md`](CHANGELOG.md) — historique des versions.

## Stack

Flask 3 · SQLite · gunicorn · PyJWT · Jinja2 · CSS pur (thème RecipeLog).
