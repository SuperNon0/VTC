# Permissions — demandées à la création de chaque site

Chaque site créé depuis le socle **choisit ses permissions**. Une permission
(*capability*) répond à la question « qui a le droit de faire ça ? » avec trois
niveaux :

| Niveau | Qui |
|---|---|
| `off` | personne (fonctionnalité **désactivée** sur ce site) |
| `membre` | tout compte **actif** (membre ou super-admin) |
| `super_admin` | **super-admin** uniquement |

> ⚠️ **À la création d'un site, il faut demander au propriétaire le niveau de
> CHAQUE permission** (voir `CLAUDE.md`). L'assistant `python -m panel.setup` pose
> les questions et remplit `.env`.

## Les permissions

| Clé (`.env`) | Fonctionnalité | Défaut |
|---|---|---|
| `CAP_ACCOUNT_MANAGEMENT` | Gestion des comptes : demandes d'accès, validation, refus, **blocage**, suppression, rôles. | `super_admin` |
| `CAP_PROFILES` | **« Se mettre à leur place »** (impersonation) : voir/éditer les données d'un membre. **N'a de sens que sur un site à données cloisonnées** (chacun ses données : films, suivi perso…). Sur un site **à données partagées** (le hub), mets `off`. | `super_admin` |
| `CAP_ADMIN_PASSWORD` | Changer le **mot de passe administrateur** dans les Paramètres. | `super_admin` |
| `CAP_SITE_UPDATE` | Bouton **« Mettre à jour le site »** (git + pip + redémarrage) et `/api/system/*`. | `super_admin` |

### Cas particulier : `CAP_ACCOUNT_MANAGEMENT`

Cette permission pilote aussi le **modèle d'accès** du site :

- **≠ `off` (ex. `super_admin`)** → site **« géré » (hub)** : un e-mail inconnu
  passe par *demande → validation → actif*, avec blocage/suppression possibles.
- **`off`** → site **« perso »** : Cloudflare a déjà filtré qui entre, donc
  l'utilisateur est **créé automatiquement en `actif`** à sa 1re visite. Pas de
  validation ni de blocage en local — ça se gère **au hub**. L'écran « Comptes »
  devient un écran **« Profils »** (voir + impersonation, selon `CAP_PROFILES`).

## Presets

`python -m panel.setup --preset <nom>` :

| Preset | account_management | profiles | admin_password | site_update |
|---|---|---|---|---|
| `hub` (la home page, données **partagées**) | super_admin | **off** | super_admin | super_admin |
| `perso` (site applicatif, données **cloisonnées**) | **off** | super_admin | super_admin | **off** |

> **« Voir en tant que » = uniquement sur les sites à données non partagées.**
> Impersonner quelqu'un n'a d'intérêt que si chacun a ses propres données. Sur le
> hub (interface partagée), `CAP_PROFILES=off` retire le bouton.

## Exemples

**Site bibliothèque de films** (accès géré au hub, tu vois et édites les listes
des membres, pas de bouton mise à jour) :

```env
CAP_ACCOUNT_MANAGEMENT=off
CAP_PROFILES=super_admin
CAP_ADMIN_PASSWORD=super_admin
CAP_SITE_UPDATE=off
```

**La home page (hub)** : tout en `super_admin` (preset `hub`).

## Qui est super-admin ? (le compte administrateur de base décide)

Il y a **un compte administrateur « de base »** par site : le super-admin qui se
connecte **en local avec le mot de passe** (amorcé par `SUPERADMIN_PASSWORD` /
`SUPERADMIN_EMAIL`). C'est le compte racine.

- **Lui seul** peut désigner d'autres super-admins : **Paramètres → Super-admins →
  « Ajouter super-admin »** (par e-mail). Il peut aussi retirer le rôle à un
  super-admin « e-mail ».
- Un **super-admin « e-mail »** (venu par Cloudflare, sans mot de passe local)
  **ne peut PAS** créer ni retirer de super-admin : il faut passer par le compte
  de base.
- Le compte de base n'est pas modifiable depuis l'UI, et le **dernier super-admin
  reste indestructible**.

Cette désignation est **par site** (dans sa table `comptes`). Sur un site perso,
l'e-mail ajouté devient super-admin dès sa prochaine connexion.

## Dans le code

- `panel/permissions.py` — registre des capabilities, `capability_level()`,
  `has_capability()`, décorateur `require_capability()`, `access_managed()`.
- Les routes sont protégées par `@require_capability("…")` (403 JSON sur `/api/*`,
  sinon redirection).
- Les templates masquent les boutons via `{% if can('…') %}` (helper injecté).
- Ajouter une permission = une entrée dans `CAPABILITIES`, une variable
  `CAP_*` dans `config.py`/`.env.example`, et les gardes correspondantes.
