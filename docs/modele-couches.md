# Modèle en couches — base verrouillée + surcouche projet

> **v2.0.0.** Ce dépôt est organisé en **deux couches** : une **base** commune
> (login Cloudflare, thème, permissions, Paramètres…) qui se met à jour toute
> seule, et une **surcouche projet** où tu ajoutes tes écrans **sans jamais
> toucher à la base**.

## Structure

```
ton-projet/
├── base/                 ← LA BASE (NON versionnée — fournie par bootstrap)
│    ├── panel/…              login, thème, permissions, Paramètres, Cloudflare…
│    └── .base-version        version installée (ex. 2.0.0)
├── app/                  ← TON PROJET (tout ce que tu ajoutes, versionné)
│    ├── __init__.py          register(flask_app) : branche tes écrans
│    ├── routes.py            tes pages
│    ├── templates/           tes écrans (priment sur ceux de la base)
│    └── schema.sql           tes tables métier
├── bootstrap_base.py     récupère base/ depuis le dépôt site-base (autonome)
├── run.py / wsgi.py      démarrage (assemble base/ + app/)
├── manage.py             commandes (setup, reset_admin, set_email, sync_base)
└── requirements.txt
```

> ### 🔑 `base/` n'est PAS versionnée dans un projet
> La base est la **source de vérité de ton dépôt site-base**, pas du projet. Dans
> un projet, `base/` est **ignorée par Git** (`.gitignore` → `base/`) et
> **récupérée** depuis site-base par `bootstrap_base.py` (à l'installation) et par
> « Mettre à jour la base » (`sync_base`). Conséquences :
> - Le dev **ne peut rien pousser qui concerne la base** — il n'y a rien de base
>   sous Git. Le verrou n'a plus de faux positif à l'import.
> - Tu changes la base **une seule fois** dans site-base → tous les projets la
>   récupèrent, toujours identique.

Sans dossier `app/`, la base tourne seule (écran de démo). Un modèle prêt à
copier est fourni : **`app.example/`** → copie-le en `app/`.

## Créer un nouveau projet

```bash
python bootstrap_base.py       # récupère base/ (fondation) depuis site-base
cp -r app.example app          # ta surcouche de départ (la seule chose versionnée)
echo "base/" >> .gitignore     # base/ n'est jamais committée dans un projet
# édite app/routes.py, app/templates/, app/schema.sql
python run.py                  # http://127.0.0.1:8000
```

> `bootstrap_base.py` prend automatiquement la dernière version « couches »
> publiée (tag `2.0.0` ou supérieur). Pour figer une version précise en prod :
> `python bootstrap_base.py --ref 2.0.0`.

## Comment la surcouche se branche (sans toucher la base)

La base (`base/panel/__init__.py`) détecte `app/` et :

| Prise | Ce que tu fournis |
|---|---|
| **Écrans** | `register(flask_app)` enregistre tes blueprints (dont l'accueil `/`). |
| **Templates** | `app/templates/` s'ajoute et **prime** sur ceux de la base. |
| **Tables** | `app/schema.sql` est exécuté en plus du schéma de la base. |
| **Accueil** | ton `/` remplace l'écran de démo ; la base retrouve l'accueil via `home_url()`. |
| **Réglages** | `flask_app.config["APP_REGLAGES_TEMPLATE"] = "app_reglages.html"` : la page `/reglages` de la base **inclut ce partial** (même thème, même cadre). |

Tu réutilises tout de la base par simple import :

```python
from panel.auth import login_required, current_compte, is_super_admin
from panel.db import get_db
# {% extends "base.html" %}  → thème + Paramètres + bandeau d'impersonation
```

**Données par utilisateur** (site cloisonné) : filtre par `current_compte()["id"]`
(compte *effectif*, impersonation incluse). Nomme la colonne `compte_id` → la base
sait réattribuer/fusionner ces lignes (cf. `set_email`).

## Deux pages, deux mises à jour (séparation base / application)

Chaque site a **deux pages de réglages** et **deux boutons de mise à jour**, tous
dessinés par la base → **identiques sur tous tes sites** :

| | Page | Met à jour | Verrouillé ? |
|---|---|---|---|
| **Site** (base) | `/parametres` | « Mettre à jour la base » (`sync_base`) | oui — dans `base/` |
| **Application** (métier) | `/reglages` | « Mettre à jour l'application » (`git` du projet) | non — c'est ton `app/` |

- La page `/parametres` et **les deux boutons** vivent dans la base verrouillée :
  leur *mécanisme* ne peut pas être cassé par la surcouche, seule la *cible* change.
- La page `/reglages` appartient à la base (cadre + thème), mais son **contenu**
  vient de ton partial `app_reglages.html` (déclaré via `APP_REGLAGES_TEMPLATE`).
  Stocke tes options avec `panel.settings.set_setting` / `get_setting` (table
  `app_settings`) — pas besoin de table dédiée. Expose-les aux templates via un
  `@bp.app_context_processor`. Voir `app.example/`.

## Mettre à jour la base (sans toucher ton projet)

- **Depuis l'app** : Paramètres → **Couche base** → « Mettre à jour la base ».
- **En commande** : `python manage.py sync_base [--ref 2.1.0]`.

Ça télécharge la dernière version du site-base et remplace **uniquement**
`base/panel/` (+ `.base-version`). Ton `app/` n'est jamais touché.

> Config : `BASE_REPO_URL` (dépôt source, défaut SuperNon0/Site-base) et
> `BASE_REPO_REF` (version précise ; sinon la dernière version « couches »).

## Règle d'or

**Ne modifie JAMAIS `base/`.** Si la base doit évoluer, la modification se fait
dans le dépôt site-base (demande-la), une version est publiée, et chaque projet
clique « Mettre à jour la base ». Tout ton travail vit dans `app/`.

**Développe le métier sur sa propre branche, indépendante de la base.** Le métier
(`app/`) et la fondation (`base/`) ne se croisent jamais dans une même branche : tes
commits ne touchent **que** `app/`. La base n'est pas versionnée avec ton métier —
elle arrive/repart via `sync_base`. Résultat : tu fais évoluer ton application sans
jamais risquer de casser (ni de figer) la base, et les mises à jour de base restent
indolores.

## Verrou : la base **ne peut pas** être modifiée (pas seulement « ne doit pas »)

Deux garde-fous, en plus de la règle ci-dessus :

- **CI GitHub** (`.github/workflows/protect-base.yml`) : tout push ou PR qui
  **modifie `base/`** dans un dépôt **projet** échoue. (Le dépôt source du
  site-base est exclu par son nom.)
- **Hook pre-commit** (`.githooks/pre-commit`) : bloque un commit local touchant
  `base/`. À activer une fois par projet :

  ```bash
  git config core.hooksPath .githooks
  ```

  Contournement volontaire (rare) : `ALLOW_BASE_EDIT=1 git commit …`.

Et rappel : `sync_base` **écrase** `base/` — toute modification locale y serait de
toute façon **effacée** à la prochaine mise à jour de la base.
