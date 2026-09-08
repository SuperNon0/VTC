# Versions & mises à jour

Les versions du site sont des **tags Git** au format `vMAJEUR.MINEUR.CORRECTIF`
(*semver*) : `v1.0.0`, `v1.1.0`, `v1.2.0`… Le bouton **Paramètres → Mise à jour**
(et `deploy/update.sh`) saute à la **dernière version publiée**, pas au dernier
commit d'une branche. Fini les noms de branches à rallonge.

> Tant qu'aucun tag `vX.Y.Z` n'existe, la mise à jour retombe automatiquement sur
> la tête de la branche courante — le bouton marche donc dès maintenant, avant
> même ta première release.

## Convention

| Partie | Quand l'incrémenter |
|---|---|
| **MAJEUR** (`v2.0.0`) | Changement incompatible (migration, rupture d'API/config). |
| **MINEUR** (`v1.1.0`) | Nouvelle fonctionnalité rétro-compatible. |
| **CORRECTIF** (`v1.0.1`) | Correction de bug, sans nouvelle fonctionnalité. |

## Publier une version (côté mainteneur)

Le travail se fait sur la branche stable (`main`). Quand tu es prêt à figer une
version :

```bash
git checkout main
git pull
# … le code est prêt et testé …
git tag -a v1.1.0 -m "v1.1.0 — description courte"
git push origin v1.1.0
```

Ou via l'interface GitHub : **Releases → Draft a new release → Choose a tag →**
`v1.1.0` **→ Publish**. C'est le moyen le plus simple (GitHub crée le tag pour toi).

Chaque serveur déployé récupère cette version au prochain clic sur **Mettre à
jour**.

## Mettre à jour un serveur

- **Depuis le site** : Paramètres → Mise à jour → **Mettre à jour** (passe à la
  dernière version, met à jour les dépendances, redémarre, affiche `vX → vY`).
- **En ligne de commande** :

  ```bash
  sudo bash /opt/site-base/deploy/update.sh          # dernière version
  sudo bash /opt/site-base/deploy/update.sh v1.0.0   # version précise (rollback)
  ```

## Revenir en arrière (rollback)

Vise explicitement une version antérieure :

```bash
sudo bash /opt/site-base/deploy/update.sh v1.0.0
```

Depuis l'API (avancé) : `POST /api/system/update` avec `{"ref": "v1.0.0"}`.

## Voir la version en cours

- Paramètres → Mise à jour (affichée en haut de la carte).
- `GET /api/system/info` → champ `version`.
- En shell : `git -C /opt/site-base describe --tags --always`.

## Note sur la branche de développement

La branche `claude/…` créée par une session d'assistant est une **branche de
travail**, pas une version. Le flux normal : fusionner ce travail dans `main`,
puis **taguer** une version. Ce sont les tags — et eux seuls — que suivent les
mises à jour.
