# VTC — fonctionnalités métier

Implémentation des besoins du cahier des charges par-dessus le template de base.
Ce document décrit **ce qui a été ajouté** ; l'auth, le thème et le déploiement
restent ceux du template (voir les autres fichiers `docs/`).

## Modèle de données (cahier §5)

Tables ajoutées dans [`panel/db.py`](../panel/db.py) :

| Table | Rôle |
|---|---|
| `courses` | Une course. Distingue `createur_id` (qui l'a saisie) et `conducteur_id` (assigné). Champs : client, adresses, `quand` (timestamp), `prix` + `prix_source` + `tarif_id`, `distance_km` (réservé §6.3), `statut`, `notes`. |
| `clients` | Clients habitués (nom, téléphone, `adresses` JSON, notes). |
| `tarifs` | Grilles tarifaires de base (libellé, prix, `concurrent` indicatif). |
| `lieux` | Lieux fréquents présélectionnables (nom + adresse). |
| `push_subscriptions` | Abonnements Web Push, un par appareil (`compte_id` → endpoint/clés). |

**Règle d'or (cahier §5)** : calendrier, notifications et statistiques se basent
sur `conducteur_id`. Le créateur ne voit « ses » courses que dans *Mes courses*.

Index `idx_courses_conducteur` / `idx_courses_createur` pour rester requêtable
par conducteur et par période (préparation des stats §6.7).

## Extraction automatique des infos client (cahier §6.1)

[`panel/ai.py`](../panel/ai.py) appelle une API IA gratuite en REST (pas de SDK,
changement de fournisseur trivial). Fournisseurs : **Gemini**, **Mistral**,
**Groq**. Le fournisseur, le modèle et la clé se règlent **dans l'app**
(*Paramètres → Extraction IA*, super-admin) et sont stockés en base
(`app_settings`) — aucune clé dans le `.env`, et bascule possible sans
redéploiement. Réponse attendue : JSON `{nom, telephone, prise_en_charge, depose}`
(parsing tolérant aux blocs ```json``` et au texte parasite).

Ajouter un fournisseur : écrire `_call_<nom>()` dans `ai.py` et l'enregistrer
dans `PROVIDERS` + `DEFAULTS` + `PROVIDER_LABELS`.

## Formulaire de course (cahier §6.2 / §6.3)

[`nouvelle_course.html`](../panel/templates/nouvelle_course.html) :

- collage d'un message client → bouton **Extraire** (si IA configurée) ;
- **autocomplétion clients** (habitués) via `/api/clients/search` ;
- **boutons de lieux fréquents** sous départ et arrivée (présélection rapide,
  saisie libre toujours possible) ;
- **prix** : liste des grilles tarifaires + option **« Autre »** (prix libre).
  Structure prête pour un futur mode `'distance'` (§6.3) sans refonte.

## Assignation & notifications (cahier §6.5)

À la création, la course est assignée à un conducteur actif (liste), puis une
notification **Web Push** part vers **tous les appareils** du conducteur assigné
([`panel/webpush.py`](../panel/webpush.py)). Pas de SMS (choix du cahier). Si le
push échoue (non installé, refusé), le calendrier reste la source fiable.

## Web Push & PWA (cahier §7)

- Clés **VAPID** générées une fois et stockées en base (`app_settings`).
- `manifest.json` + `sw.js` (servi à la racine, scope `/`) → installable iOS/Android.
- **iOS 16.4+** : le push exige que l'app soit d'abord ajoutée à l'écran d'accueil.
  Le calendrier affiche un rappel explicite pour les conducteurs iPhone.
- Endpoints : `GET /api/push/key`, `POST /api/push/subscribe`, `POST /api/push/unsubscribe`.

## Calendrier & export natif (cahier §6.6)

- Dashboard = calendrier personnel du conducteur (courses assignées à venir,
  groupées par jour). Chaque événement est **cliquable** → page de détail.
- **Page détail** (`/course/<id>`) : toutes les infos (client, habitué/nouveau,
  téléphone, départ, arrivée, prix, conducteur, créateur, notes). Le **statut se
  met à jour ici, dans l'app** (boutons → `POST /api/courses/<id>/statut`) — pas
  depuis l'événement figé exporté vers le calendrier natif du téléphone.
- Bouton **Ajouter à mon agenda** : détecte iOS → fichier `.ics`
  (`/course/<id>/ics`) ; sinon → lien **Google Agenda** (`/course/<id>/google`).

### Modèle d'événement personnalisable (Paramètres → Modèle calendrier)

Le **titre** et les **notes** de l'événement sont construits depuis deux modèles
texte à **placeholders** entre crochets, modifiables par le **super-admin**
(`/parametres/calendrier`, avec aperçu en direct). Implémentation :
[`panel/utils.py`](../panel/utils.py) (`course_titre` / `course_description`,
substitution `[clé] → valeur`), modèles stockés dans `app_settings`
(`cal_title_template`, `cal_notes_template`) ; vide = valeur par défaut.

Placeholders : `[nom]`, `[telephone]`, `[depart]`, `[arrivee]`, `[prix]`,
`[date]`, `[statut]`, `[habitue]` (« Habitué » si la course est liée à un client
enregistré, sinon « Nouveau client »), `[notes]`.

Valeurs par défaut :

- **Titre** : `[nom] · [depart] → [arrivee]`
- **Notes** :
  ```
  Client : [nom] ([habitue])
  Téléphone : [telephone]
  Départ : [depart]
  Arrivée : [arrivee]
  Prix : [prix]
  Date : [date]
  Notes : [notes]
  ```

Pour modifier : ouvrir *Paramètres → Modèle calendrier*, cliquer un placeholder
pour l'insérer (ou le taper à la main, ex. `Prix : [prix]`), vérifier l'aperçu,
*Enregistrer*. *Réinitialiser* rétablit les valeurs par défaut. Un placeholder
sans valeur pour une course donnée devient une chaîne vide.

## Statistiques (cahier §6.7 — différé)

Vue **unique** `/mes-stats` (aperçu du mois : nb de courses + CA des courses
terminées). Le super-admin la consulte pour un conducteur via « voir en tant
que » (impersonation) — **pas d'écran séparé**. Le détail complet est reporté ;
les colonnes nécessaires sont déjà en place et indexées.

## Rôles (cahier §3)

`super_admin` et `membre` (= conducteur). Le super-admin est aussi conducteur.
N'importe quel conducteur peut créer et assigner une course, à quiconque ou à
lui-même. Réglages réservés au super-admin : **extraction IA** (clé API) et
**grilles tarifaires** (prix). Gérables par **tout conducteur actif** : les
**lieux fréquents** (liste collaborative, complétée au fur et à mesure) et les
**clients habitués**.
