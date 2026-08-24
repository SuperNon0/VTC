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
redéploiement. Réponse attendue : JSON
`{nom, telephone, prise_en_charge, depose, date_heure}` (parsing tolérant aux
blocs ```json``` et au texte parasite).

La **date courante est injectée dans le prompt** pour résoudre les expressions
relatives (« demain », « après-demain », « dans 3 jours », « lundi prochain »,
« midi trente »…). `date_heure` est renvoyée au format `AAAA-MM-JJTHH:MM`
(normalisée côté serveur) et pré-remplit le champ date/heure du formulaire.

Ajouter un fournisseur : écrire `_call_<nom>()` dans `ai.py` et l'enregistrer
dans `PROVIDERS` + `DEFAULTS` + `PROVIDER_LABELS`.

## Formulaire de course (cahier §6.2 / §6.3)

[`nouvelle_course.html`](../panel/templates/nouvelle_course.html) :

- collage d'un message client → bouton **Extraire** (si IA configurée) ;
- **autocomplétion clients** (habitués) via `/api/clients/search` ;
- **lieux tapés** : départ et arrivée s'autocomplètent depuis les lieux
  configurés (taper « gare aigues-mortes » propose le lieu ; le choisir remplit
  l'adresse enregistrée). Saisie libre toujours possible. Les lieux et les
  tarifs sont embarqués en JSON dans la page (pas d'aller-retour serveur).
- **prix auto** : si le départ ET l'arrivée correspondent à un tarif
  place-à-place, ce tarif est **sélectionné automatiquement** (modifiable) ;
  l'option **« Autre »** (prix libre) reste toujours disponible.

### Grilles tarifaires place-à-place (cahier §6.3)

Un tarif relie un **lieu de départ** à un **lieu d'arrivée** (`lieu_depart_id` /
`lieu_arrivee_id`, l'un des deux peut être vide pour un forfait à sens unique).
Le libellé est **généré** (« Départ → Arrivée ») — pas de saisie en double. Le
champ « concurrent » a été retiré (inutile). L'auto-sélection compare les lieux
choisis du départ/arrivée aux tarifs (score : deux côtés > un côté).

## Assignation & notifications (cahier §6.5)

À la création, la course est assignée à un conducteur actif (liste), puis une
notification **Web Push** part vers **tous les appareils** du conducteur assigné
([`panel/webpush.py`](../panel/webpush.py)). Pas de SMS (choix du cahier). Si le
push échoue (non installé, refusé), le calendrier reste la source fiable.

### Message de notification personnalisable + test

*Paramètres → Notifications* (super-admin) : le **titre** et le **texte** de la
notification d'assignation se composent avec des placeholders `[nom]`,
`[telephone]`, `[depart]`, `[arrivee]`, `[prix]`, `[date]`, `[duree]`
(stockés dans `app_settings` : `push_title_template` / `push_body_template`,
défauts sinon). Un **bouton de test par conducteur** envoie un push de
vérification à ses appareils (message clair si aucun appareil n'est abonné).

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
`[date]`, `[duree]` (durée de trajet estimée), `[statut]`, `[habitue]`
(« Habitué » si la course est liée à un client enregistré, sinon « Nouveau
client »), `[notes]`.

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

## Estimation du temps de trajet (OpenStreetMap)

[`panel/maps.py`](../panel/maps.py) : à la création d'une course, si le départ et
l'arrivée sont renseignés, on estime **durée + distance** via **Nominatim**
(géocodage) puis **OSRM** (itinéraire voiture) — services publics **gratuits,
sans clé**. Résultat stocké dans `courses.duree_min` / `courses.distance_km`,
affiché sur la page détail (bouton **↻ Estimer** pour recalculer,
`POST /course/<id>/estimer`) et exploitable via le placeholder `[duree]`.

Best-effort : ne bloque jamais la création (réseau injoignable, adresse non
géocodée → simplement pas d'estimation). Activable/désactivable par le
super-admin (*Paramètres*, clé `maps_enabled`). Respecte la politique Nominatim
(User-Agent explicite, faible volume).

## Navigation (barre du bas)

Navigation mobile-first : une **barre d'onglets fixe en bas**
([`base.html`](../panel/templates/base.html)) — Accueil (calendrier), Courses
(mes courses créées), bouton central **+** (nouvelle course), Clients, et
**Plus** ([`plus.html`](../panel/templates/plus.html)) qui regroupe stats,
lieux, et pour le super-admin les réglages + la déconnexion. Icônes SVG inline
(aucune police externe), onglet actif en doré.

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
