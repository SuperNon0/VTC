# Changelog

Toutes les versions notables du **site de base**. Les versions sont des tags Git
`vMAJEUR.MINEUR.CORRECTIF` (voir [`docs/versions.md`](docs/versions.md)). Le bouton
**Paramètres → Mise à jour** (et `deploy/update.sh`) saute à la dernière version
publiée.

---

## v1.1.0 — 2026-08-17

Grosse mise à jour : permissions par site, gestion des super-admins, config
Cloudflare dans l'UI + diagnostic, mise à jour sans sudo, et documentation
complète. **Rétro-compatible** : par défaut, un site se comporte comme en v1.0.0.

### Ajouté
- **Permissions par site (capabilities).** Chaque fonctionnalité a un niveau
  `off` / `membre` / `super_admin`, **à demander à la création** : gestion des
  comptes, profils + « se mettre à leur place », mot de passe admin, bouton de
  mise à jour. Assistant `python -m panel.setup` (+ presets `hub` / `perso`).
  Voir [`docs/permissions.md`](docs/permissions.md).
- **Deux profils de site.** *Hub* (données partagées : gestion des comptes on,
  impersonation off) et *perso* (données cloisonnées : accès auto en `actif`,
  impersonation on).
- **Bouton « Ajouter un super-admin »** (Paramètres → Super-admins), **réservé au
  compte administrateur de base** (login local). Un super-admin « e-mail » ne peut
  pas désigner de super-admin.
- **Config Cloudflare éditable dans l'UI** (Paramètres → « Cloudflare / Accès »),
  stockée en base (`app_settings`, prioritaire sur `.env`) via `panel/settings.py`.
  Champ « Équipe » normalisé (nom seul).
- **Écran Diagnostic** intégré à « Cloudflare / Accès » : boutons **Enregistrer**
  et **Tester** (teste en direct les valeurs saisies via `POST /api/cf-test`),
  résultat affiché juste en dessous (jeton reçu, en-tête e-mail, équipe/AUD,
  vérif JWT `OK ✓` / `échec ✗` + détail) — `auth.cf_diagnostic()`.
- **Guide développeur** [`docs/guide-developpeur.md`](docs/guide-developpeur.md)
  (architecture, rôle de chaque fichier, *pourquoi*, recettes) et ce `CHANGELOG.md`.
- **Installation en une commande** (`install.sh`) avec `ADMIN_EMAIL` / `ADMIN_PASSWORD` :
  le super-admin est créé d'emblée (mot de passe généré et affiché si absent), le
  service démarre tout seul.
- **Rattacher / changer l'e-mail Google de l'admin** : commande serveur
  `deploy/set_email.sh <email>` (fusionne un doublon en réattribuant les données
  par `compte_id`, **sans rien perdre**) ; réglage UI **Paramètres → Mon e-mail
  Google** ; module `python -m panel.set_email`.

### Modifié
- **Mise à jour du site sans sudo** : rechargement par **`SIGHUP` au master
  gunicorn** (le service se recharge lui-même) au lieu de `sudo systemctl restart`.
  Règle sudoers supprimée de `install_lxc.sh`.
- **`GET /login`** redirige vers `/gateway` (plus de 405) ; page de login en
  colonne (messages flash **au-dessus** de la carte).
- **`_seed_superadmin`** rattache `SUPERADMIN_EMAIL` à un super-admin existant sans
  e-mail. Jeton Cloudflare aussi lu via le cookie `CF_Authorization` ; cache JWK
  par équipe.
- **« Voir en tant que »** disponible uniquement sur les sites à données
  cloisonnées (`CAP_PROFILES`), retiré du hub.

### Sécurité
- `/api/*` renvoie `401`/`403` JSON quand l'accès est refusé (au lieu d'une
  redirection), en plus du `Cache-Control: no-store`.

---

## v1.0.0 — Fondation

Première version du socle réutilisable.

### Ajouté
- **Thème « RecipeLog »** (dark + accent doré, DM Serif Display / DM Mono),
  reproduit à l'identique des maquettes. [`docs/theme-recipelog.md`](docs/theme-recipelog.md).
- **Authentification v2 multi-comptes derrière Cloudflare Zero Trust** :
  vérification du JWT (`RS256` + `aud` + `iss`), login local par mot de passe (LAN),
  cycle de vie `pending → actif / refused / bloque`, rôles `super_admin` / `membre`,
  « voir en tant que » (impersonation) + bandeau, journal d'audit, dernier
  super-admin indestructible, `/api/*` en `no-store`.
  [`docs/authentification-v2.md`](docs/authentification-v2.md).
- **Écrans d'auth** fidèles aux maquettes (login, demande, attente, refus, bloque,
  comptes, bandeau).
- **Changement du mot de passe admin** (Paramètres) + **« mot de passe oublié »**
  (commande serveur) + CLI `python -m panel.reset_admin`.
- **Notifications via BotPanel** (`notify(slug, **vars)`).
  [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md).
- **Bouton « Mettre à jour »** par **versions (tags `vX.Y.Z`)** + rollback.
  [`docs/versions.md`](docs/versions.md).
- **Comportement « app native » mobile** (anti-zoom).
  [`docs/mobile-anti-zoom.md`](docs/mobile-anti-zoom.md).
- **Déploiement Proxmox** (LXC/VM) + tunnel Cloudflare : `install_lxc.sh`,
  service systemd, `update.sh`. [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md).
