<div align="center">

# VTC — Gestion des courses

**Application web (installable comme une app sur mobile) pour gérer une activité de
taxi / VTC.** Planifie tes courses, gère tes clients et tes tarifs, reçois des
notifications, suis tes statistiques et exporte vers ton calendrier — le tout dans
une interface sombre soignée, sécurisée derrière **Cloudflare**, et qui **fonctionne
même hors connexion** (en lecture).

Thème « RecipeLog » (dark + doré) · PWA installable · multi-conducteurs.

</div>

---

## À quoi sert ce site ?

C'est le **poste de commande d'un chauffeur (ou d'une petite équipe) de taxi/VTC**.
Depuis ton téléphone (ajouté à l'écran d'accueil comme une vraie app) ou ton
ordinateur, tu peux :

- **saisir une course** en quelques secondes (ou coller le message d'un client et
  laisser l'IA remplir les champs),
- **planifier** : chaque course a une date/heure, un départ, une arrivée, un prix et
  un **conducteur assigné** ;
- **suivre l'avancement** : « à faire » → « en cours » → « terminée » (ou annulée) ;
- **gérer tes clients habitués, tes lieux fréquents et tes grilles de tarifs** pour
  ressaisir une course répétitive en un clic ;
- **être prévenu** par notification à chaque course assignée ;
- **ajouter la course à ton agenda** (iPhone / Google) ;
- **analyser ton activité** (chiffre d'affaires, courses, meilleurs clients…).

Deux rôles : **toi** (super-admin, appelé « admin » dans l'app, tu gères tout) et les
**conducteurs**. Une course est créée par quelqu'un puis assignée à un conducteur, qui
la voit dans son calendrier et reçoit une notification.

---

## Fonctionnalités

### 📅 Calendrier / Accueil
- Trois vues : **Liste**, **Mois**, **Semaine** (l'app **retient ta dernière vue**).
- **Filtres** : par statut (À faire, En cours, Terminées, Annulées, Toutes), par jour
  (Aujourd'hui, Demain, un **jour précis**, une **période**), par **conducteur**, et
  **tri** (par date de course ou par date d'ajout).
- Le **jour de la semaine** est affiché ; une course passe **automatiquement** en
  « en cours » à son heure, et reste ainsi jusqu'à ce que tu la marques « terminée ».
- Cartes **colorées par statut** (liseré à gauche) pour repérer d'un coup d'œil.

### ➕ Créer / modifier une course
- **Extraction IA** : colle le message d'un client, l'app remplit le nom, le
  téléphone, les adresses et l'heure (fournisseurs gratuits : **Gemini, Mistral,
  Groq** — au choix, sans carte bancaire).
- Saisie guidée : on choisit **la ville puis l'adresse** (filtrée par ville), avec
  **lieux fréquents** et **adresses habituelles du client** proposés en un clic.
- **Bascule « Note »** sur un champ départ/arrivée : quand ce n'est pas une vraie
  adresse (« devant la boulangerie »), on le marque comme note → **pas de ville
  ajoutée, pas d'estimation**.
- **Inverser** départ ↔ arrivée, **dupliquer** une course (sans l'horaire),
  **modifier** une course existante.
- **Prix** : grille tarifaire **sélectionnée automatiquement** selon le trajet, ou
  prix libre.
- **Estimation** durée + distance calculée **en arrière-plan** (l'ajout reste
  instantané).
- **Liens Google Maps** acceptés dans une adresse : au clic ils s'ouvrent **dans
  Waze**, et servent aussi à **estimer** le trajet.

### 👤 Clients habitués
- Nom + **téléphone toujours formaté** (06 12 34 56 78) + **plusieurs adresses
  nommées** (Maison, Travail…).
- **Autocomplétion** à la création d'une course (nom → téléphone + notes se
  remplissent), **détection de doublon** de numéro.
- Adresses **cliquables** partout (ouvrir dans Waze / Maps / copier), téléphones
  cliquables pour appeler.

### 🏙️ Villes, lieux fréquents & tarifs
- **Villes desservies** : liste gérable (ajout à l'unité ou **coller une liste**).
- **Lieux fréquents** (gares, aéroports, points récurrents), chacun rattaché à une
  ville, servant de **boutons de présélection** dans le formulaire.
- **Grilles tarifaires** : un tarif relie un **départ** à une **arrivée**, chaque
  extrémité pouvant être une **ville** ou un **lieu**. Tarif **bidirectionnel** (↔)
  pour couvrir l'aller **et** le retour d'un seul coup.

### 📊 Statistiques (interactives)
- **Filtre de période** : ce mois-ci, mois dernier, 90 jours, année, **personnalisé
  (du…au)**, tout l'historique.
- **Indicateurs cliquables** (CA réalisé, CA à venir, nombre de courses, terminées,
  prix moyen, distance, temps de conduite, taux d'annulation, clients) : un **« i »**
  ouvre une pop-up qui **explique chaque chiffre**.
- **Graphiques tactiles** : chiffre d'affaires par jour/mois, courses par jour de la
  semaine, répartition par statut, meilleurs clients — **touche une barre** pour voir
  la valeur exacte.

### 🔔 Notifications (Web Push)
- Une **alerte est envoyée au conducteur** à chaque course qui lui est assignée
  (technologie Web Push / VAPID, fonctionne en PWA).
- **Message personnalisable** (titre + texte, avec des variables entre crochets) et
  **bouton de test** pour vérifier les appareils d'un conducteur.

### 🗓️ Export vers le calendrier
- Une course s'ajoute à ton agenda **iPhone (.ics)** ou **Google Agenda**, avec
  l'**heure locale correcte** (pas de décalage horaire).

### ❓ Aide contextuelle
- Partout où c'était utile, un petit **« ? »** à côté d'une fonctionnalité ouvre une
  **mini pop-up d'explication** — l'interface reste épurée, l'aide est à un clic.

---

## Application installable (PWA)

Le site s'installe **comme une application** sur l'écran d'accueil (iPhone : Partager
→ « Sur l'écran d'accueil »). Une fois installé :

- **Plein écran**, sans barre de navigateur, avec une **barre de navigation en bas**
  fiable (fini le bug iOS où elle « décrochait »).
- **Lancement rapide** : le service worker met en cache le style et les icônes.
- **Mode hors ligne (lecture)** : sans réseau, l'app **réaffiche les dernières pages
  consultées** au lieu d'une erreur. *(La création de course hors ligne n'est pas
  encore gérée — voir « Idées / suite ».)*

---

## Nouveautés récentes

Les derniers ajouts et correctifs apportés à l'application :

- **Statistiques avancées et interactives** (période, indicateurs expliqués,
  graphiques tactiles).
- **Bascule « Note »** pour distinguer une vraie adresse d'un simple repère.
- **Aide « ? » contextuelle** qui remplace les longs textes explicatifs.
- **Mode hors ligne** (lecture) + **cache PWA** pour un démarrage plus rapide.
- **Ajout de course instantané** : l'estimation de trajet et l'envoi de la
  notification se font **en arrière-plan** (avant, l'ajout pouvait attendre 20–30 s
  le réseau).
- **Corrections** : barre de navigation iOS qui décrochait, **heure décalée** à
  l'export calendrier, **cartes qui devenaient jaunes**, **fiabilité de la base de
  données** (plus de risque de perdre une estimation), **anti double-création** de
  course.

Historique complet de la couche fondation : [`CHANGELOG.md`](CHANGELOG.md).

---

## Sécurité & fiabilité (en bref)

- **Accès protégé par Cloudflare Zero Trust** : l'e-mail est vérifié par **JWT**
  (`RS256` + `aud`), avec un login local par mot de passe en réseau local.
- Les **données sont enregistrées immédiatement** sur le serveur (SQLite) à chaque
  action ; la base attend un verrou au lieu d'échouer (`busy_timeout`).
- Les réponses `/api/*` sont en **`no-store`**, le dernier super-admin est
  indestructible, anti-force-brute au login.

---

## Architecture — deux couches

Ce dépôt est organisé en **deux couches** ; c'est important à comprendre pour le
développement :

- **`base/`** = la **fondation verrouillée** (login, thème, permissions, page
  Paramètres, mécanisme de mise à jour). **On n'y touche jamais** : elle se met à jour
  toute seule (Paramètres → « Mettre à jour la base »). Elle **n'est pas versionnée**
  dans le projet (fournie par `bootstrap_base.py`).
- **`app/`** = **le métier VTC** (tous les écrans et tables décrits ci-dessus). **Tout
  le travail se fait ici.**

> 📖 Contrat de développement complet : [`CLAUDE.md`](CLAUDE.md) · modèle détaillé :
> [`docs/modele-couches.md`](docs/modele-couches.md) · spec métier :
> [`docs/taxi-vtc.md`](docs/taxi-vtc.md).

**Deux pages de réglages, deux mises à jour :**

| | Page | Bouton | Concerne |
|---|---|---|---|
| **Site** (fondation) | `/parametres` | « Mettre à jour la base » | Cloudflare, comptes, socle |
| **Application** (métier) | `/reglages` | « Mettre à jour le site » | tes courses, tarifs, lieux… |

---

## Démarrage (dev local, sans Cloudflare)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Dans `.env`, au minimum :

```env
SECRET_KEY=une-longue-chaine-aleatoire
SUPERADMIN_PASSWORD=tonMotDePasse       # login en local
CF_VERIFY_JWT=false                       # dev sans Cloudflare
ALLOW_LOCAL_LOGIN=true
```

Puis :

```bash
python run.py            # → http://127.0.0.1:8000  (connexion avec SUPERADMIN_PASSWORD)
```

`run.py` assemble automatiquement `base/` + `app/`.

---

## Installation (Proxmox + Cloudflare)

En une commande, depuis le shell d'un nœud **Proxmox** (crée le conteneur LXC **et**
installe l'app dedans) :

```bash
ADMIN_EMAIL=toi@gmail.com \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/VTC/main/install.sh)"
```

> Options : `CTID=130 STORAGE=local-lvm BRIDGE=vmbr0 ADMIN_PASSWORD=… REPO_REF=… BIND=0.0.0.0:8000`.
> Pour exposer publiquement, place un **tunnel Cloudflare** devant et passe
> `CF_VERIFY_JWT=true` + `SESSION_COOKIE_SECURE=true`.

Sur un conteneur/VM déjà prêt : `sudo bash deploy/install_lxc.sh`.
Guide complet : [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md).

---

## Commandes & tests

```bash
python manage.py setup [--preset hub|perso]   # pose les permissions, écrit .env
python manage.py reset_admin ["nouveau_mdp"]  # réinitialise le mot de passe admin
python manage.py set_email <email> | --clear  # rattache/fusionne l'e-mail admin
python manage.py sync_base [--ref 2.1.0]      # met à jour la couche base/

python tests/test_site.py                     # batterie de vérifications (base + métier)
```

Diagnostics serveur : `deploy/check_timezone.sh` (fuseau horaire),
`deploy/check_estimation.sh` (connectivité géocodage / itinéraire).

---

## Idées / suite

- **Mode hors ligne — écriture** : créer une course sans réseau et l'**envoyer plus
  tard** (à la prochaine ouverture avec connexion). *(Non implémenté — sur iPhone la
  synchro automatique en arrière-plan n'est pas fiable.)*

---

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — contrat de développement (à lire en premier).
- [`docs/taxi-vtc.md`](docs/taxi-vtc.md) — spécification métier VTC.
- [`docs/modele-couches.md`](docs/modele-couches.md) — base verrouillée + surcouche.
- [`docs/guide-developpeur.md`](docs/guide-developpeur.md) — comprendre le code.
- [`docs/authentification-v2.md`](docs/authentification-v2.md) — spec de l'auth (sécurité).
- [`docs/theme-recipelog.md`](docs/theme-recipelog.md) — cahier des charges du thème.
- [`docs/permissions.md`](docs/permissions.md) — permissions par site.
- [`docs/notifications-botpanel.md`](docs/notifications-botpanel.md) — notifications BotPanel.
- [`docs/deploiement-proxmox.md`](docs/deploiement-proxmox.md) — Proxmox + Cloudflare.
- [`docs/mobile-anti-zoom.md`](docs/mobile-anti-zoom.md) — comportement « app native » mobile.
- [`docs/versions.md`](docs/versions.md) — versionnage & rollback.
- [`CHANGELOG.md`](CHANGELOG.md) — historique des versions.

## Stack

Flask 3 · SQLite · gunicorn · PyJWT · Jinja2 · CSS pur (thème RecipeLog) ·
PWA (service worker + Web Push).
