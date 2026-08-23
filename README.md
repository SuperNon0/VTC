<div align="center">

# site-base

**Fondation réutilisable pour démarrer un projet web** — thème « RecipeLog »
(dark + doré), authentification multi-comptes derrière **Cloudflare Zero Trust**,
et notifications **BotPanel** intégrées.

</div>

---

Ce dépôt est un **template**. On le clone pour chaque nouveau projet : le thème,
le login v2 et les notifications sont déjà en place, il n'y a qu'à ajouter les
écrans métier. Il est pensé pour être **repris à l'identique** par un développeur
(y compris un assistant IA) — voir [`CLAUDE.md`](CLAUDE.md).

## Fonctionnalités

- 🎨 **Thème RecipeLog** — dark-only, accent doré `#e8c547`, DM Serif Display +
  DM Mono. CSS pur, tokens dans `:root`. Rendu fidèle aux maquettes de référence.
- 🔐 **Auth v2 multi-comptes** — cycle de vie `pending → actif / refused / bloqué`,
  rôles `super_admin` / `membre`, « voir en tant que » (impersonation) avec bandeau,
  journal d'audit.
- ☁️ **Cloudflare Zero Trust** — e-mail Google comme portier, **vérification du
  JWT** `Cf-Access-Jwt-Assertion` + `aud`, login local par mot de passe en LAN.
- 🔔 **Notifications BotPanel** — helper `notify(slug, **vars)`, branché sur le
  cycle de vie des comptes, désactivable via `.env`.
- 📦 **Déploiement Proxmox** — script LXC + service systemd + tunnel Cloudflare.

## Démarrage rapide (dev local)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Renseigne au minimum SECRET_KEY et SUPERADMIN_PASSWORD dans .env
python run.py            # → http://127.0.0.1:8000
```

Sans Cloudflare en local, connecte-toi avec le `SUPERADMIN_PASSWORD` (accès LAN).

## Écrans

| Écran | Quand | Template |
|---|---|---|
| Login local | Accès LAN (mot de passe super-admin) | `login.html` |
| Demander un accès | E-mail CF autorisé mais inconnu | `demande.html` |
| En attente | Compte `pending` | `attente.html` |
| Refusé | Compte `refused` | `refus.html` |
| Suspendu | Compte `bloqué` | `bloque.html` |
| Comptes (gestion) | Super-admin | `comptes.html` |
| Bandeau impersonation | « Voir en tant que » actif | `base.html` |
| Dashboard démo | Connecté | `dashboard.html` (à remplacer) |

Maquettes de référence + captures : [`docs/maquettes-auth-v2/`](docs/maquettes-auth-v2/).

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — contrat de reproduction (à lire en premier).
- [`docs/theme-recipelog.md`](docs/theme-recipelog.md) — cahier des charges du thème.
- [`docs/authentification-v2.md`](docs/authentification-v2.md) — spec complète de l'auth.
- [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md) — intégration BotPanel.
- [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md) — guide Proxmox + Cloudflare.

## Stack

Flask 3 · SQLite · gunicorn · PyJWT · Jinja2 · CSS pur (thème RecipeLog).

## Personnaliser pour ton projet

1. Marque : `BRAND_PREFIX` / `BRAND_SUFFIX` / `BRAND_BADGE` dans `.env`, logo `panel/static/logo.svg`.
2. Contenu : remplace `dashboard.html` + `routes/main.py` par tes écrans.
3. Données : ajoute tes tables (décide **partagé vs cloisonné**, cf. spec §7).

Ne modifie pas le thème ni la sécurité de l'auth sans raison — voir `CLAUDE.md`.
