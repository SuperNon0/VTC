# Prompt de migration (à donner au dev IA)

Copie-colle le bloc ci-dessous à l'assistant qui migre un site existant vers le
modèle en couches. Il intègre les deux garde-fous : **base non versionnée** et
**développement sur une branche dédiée**.

> Adapte `BASE_REPO_REF` : une fois la version `2.0.0` du site-base publiée,
> remplace `claude/v2-modele-couches` par `2.0.0` (ou retire la variable pour
> prendre la dernière version publiée).

---

```text
CONTEXTE
Ce site doit adopter le « site-base », une fondation en DEUX COUCHES :
- base/ = la fondation (login Cloudflare, thème, permissions, page Paramètres,
  mises à jour). Elle est NON VERSIONNÉE dans le projet : fournie par le dépôt
  site-base, récupérée par bootstrap_base.py. On n'y touche JAMAIS.
- app/ = LE MÉTIER : les écrans et les données propres à CE site. C'est la SEULE
  chose que tu versionnes et modifies.
Référence : https://github.com/SuperNon0/Site-base (branche claude/v2-modele-couches).
Lis d'abord, dans ce dépôt : README.md, CLAUDE.md, docs/modele-couches.md.

TA MISSION — migrer ce site existant vers ce modèle SANS perdre de données ni
casser le site en production.

1) TRAVAILLE SUR UNE BRANCHE DÉDIÉE (ex. claude/migration-nouveau-socle), JAMAIS
   sur main. main reste la version STABLE en production. Ne merge PAS toi-même.

2) Récupère l'ossature du projet en couches depuis site-base : run.py, wsgi.py,
   manage.py, bootstrap_base.py, requirements.txt, .env.example, deploy/,
   .github/workflows/protect-base.yml, .githooks/pre-commit, app.example/.

3) base/ NON VERSIONNÉE :
   - Ajoute « base/ » au .gitignore. base/ ne doit JAMAIS être committée.
   - Récupère la fondation en local pour faire tourner le site :
       BASE_REPO_REF=claude/v2-modele-couches python bootstrap_base.py
   - Si base/ était déjà committée : git rm -r --cached base/ (garde les fichiers).

4) Déplace TOUT le code métier actuel dans app/ :
   - écrans   -> app/routes.py + app/templates/ ( {% extends "base.html" %} )
   - tables   -> app/schema.sql
   - réglages -> app/templates/app_reglages.html (+ dans app/__init__.py :
                 flask_app.config["APP_REGLAGES_TEMPLATE"] = "app_reglages.html")
   Réutilise la base par import : from panel.auth import login_required,
   current_compte ; from panel.db import get_db ; from panel.settings import
   get_setting, set_setting.

5) Préserve les données : garde le même schéma (ou fournis une migration). Si le
   métier est par-utilisateur, relie chaque ligne à une colonne compte_id et
   filtre par current_compte()["id"].

6) Active le verrou local : git config core.hooksPath .githooks

RÈGLES ABSOLUES
- NE MODIFIE JAMAIS base/. Si tu crois qu'il faut le changer, ARRÊTE-TOI et
  demande-moi : ça se fait dans le dépôt site-base, pas ici.
- Le métier (app/) et la fondation (base/) ne se mélangent jamais.
- base/ n'apparaît nulle part dans Git (ni dans un commit, ni dans une PR).

AVANT DE DIRE QUE C'EST FINI
- git status : AUCUN fichier base/ suivi (git ls-files base/ doit être VIDE).
- python bootstrap_base.py puis python run.py : login + écrans métier +
  /parametres + /reglages fonctionnent.
- Si le dépôt site-base a une batterie de tests, lance-la (python tests/test_site.py).

À ME LIVRER
- La branche poussée (SANS merge dans main), base/ non versionnée.
- Un court résumé : ce qui est passé dans app/, comment les données sont
  préservées, et comment tester.
```

---

## Variante « nouveau site » (partir de zéro)

Même bloc, en remplaçant l'étape 4 par « crée tes écrans dans `app/` à partir de
`app.example/` » — il n'y a pas de métier existant à déplacer.
