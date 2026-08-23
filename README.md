<div align="center">

# VTC — gestion d'activité taxi

**Application web (PWA)** de gestion des courses pour une équipe de conducteurs :
calendrier personnel, création/assignation de course, extraction IA des infos
client, grilles tarifaires, notifications Web Push. Construite sur le template
`SuperNon0/site` (thème « RecipeLog » + auth **Cloudflare Zero Trust**).

</div>

---

Un super-admin (également conducteur) et plusieurs conducteurs. N'importe quel
conducteur peut créer une course et l'assigner à qui il veut — pas de rôle
« dispatcher » séparé. Chaque conducteur voit son propre calendrier des courses
qui **lui sont assignées** et reçoit une notification à chaque nouvelle course.

## Fonctionnalités

- 📅 **Calendrier personnel** — courses assignées à venir, groupées par jour,
  statut modifiable ; export vers l'agenda natif (`.ics` iPhone / Google Agenda Android).
- ➕ **Création de course** — extraction IA d'un message client, autocomplétion
  des clients habitués, boutons de lieux fréquents, prix par grille ou libre.
- 🤖 **Extraction IA configurable** — Gemini / Mistral / Groq (gratuits, sans
  carte). Fournisseur + clé réglables **dans l'app** (super-admin), sans redéploiement.
- 🔔 **Web Push (PWA)** — alerte à l'assignation ; iOS 16.4+ après ajout à l'écran d'accueil.
- 💶 **Grilles tarifaires** — prix de base préenregistrés + option « Autre ».
- 👤 **Clients habitués** — base recherchable, retrouvés à la création d'une course.
- 🔐 **Auth v2** — Cloudflare Zero Trust + login local LAN, rôles, « voir en tant que ».
- 📱 **PWA** — installable iOS/Android (manifest + service worker).

## Démarrage rapide (dev local)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Renseigne au minimum SECRET_KEY et SUPERADMIN_PASSWORD dans .env
python run.py            # → http://127.0.0.1:8000
```

Sans Cloudflare en local, connecte-toi avec le `SUPERADMIN_PASSWORD` (accès LAN).
Ensuite, dans *Paramètres* (super-admin) : configure l'extraction IA, les grilles
tarifaires et les lieux fréquents.

## Documentation

- [`docs/taxi-vtc.md`](docs/taxi-vtc.md) — **fonctionnalités métier** (à lire en premier).
- [`CLAUDE.md`](CLAUDE.md) — contrat de reproduction + décisions structurantes.
- [`docs/authentification-v2.md`](docs/authentification-v2.md) — spec de l'auth.
- [`docs/theme-recipelog.md`](docs/theme-recipelog.md) — cahier du thème.
- [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md) — BotPanel (comptes).
- [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md) — Proxmox + Cloudflare.

## Stack

Flask 3 · SQLite · gunicorn · PyJWT · pywebpush · Jinja2 · CSS pur (thème RecipeLog).

Ne modifie pas le thème ni la sécurité de l'auth sans raison — voir `CLAUDE.md`.
