# Notifications — intégration BotPanel

Le site de base envoie ses notifications via **BotPanel**
(<https://github.com/SuperNon0/botpanel>), pas directement à Discord. Le principe :

1. Tu crées la notification **une fois** dans BotPanel (titre, message, couleur,
   channel, boutons…) et tu lui donnes un **slug** (identifiant).
2. Le site envoie un simple `POST {BOTPANEL_URL}/api/notify` avec ce slug (+ des
   variables optionnelles).
3. BotPanel s'occupe de toute la mise en forme et de l'envoi Discord.

> ✅ Le site n'a **rien à savoir** de Discord. Tu changes la notification quand tu
> veux dans BotPanel sans retoucher le code.

---

## Ce qui est déjà câblé dans le site de base

Le helper est dans [`panel/notify.py`](../panel/notify.py) :

```python
from panel.notify import notify

notify("mon_slug")                                  # simple
notify("backup_done", vmid="100", duree="2m34s")    # avec variables {var:...}
```

- Il lit `BOTPANEL_URL` dans la config (`.env`). **Si vide → les notifications
  sont désactivées** (aucune erreur, le site fonctionne normalement).
- Il **n'échoue jamais** : une notification injoignable est seulement journalisée,
  elle ne casse pas la requête métier.
- Les `variables` remplissent les `{var:nom}` du template BotPanel.

### Notifications du cycle de vie des comptes (déjà branchées)

| Événement | Fonction appelée | Slug (`.env`) | Variables envoyées |
|---|---|---|---|
| Nouvelle demande d'accès | `auth.request_access` | `NOTIFY_SLUG_ACCESS_REQUEST` (`acces_demande`) | `email` |
| Compte validé | `accounts.valider` | `NOTIFY_SLUG_ACCESS_VALIDATED` (`acces_valide`) | `email` |
| Compte bloqué | `accounts.bloquer` | `NOTIFY_SLUG_ACCESS_BLOCKED` (`acces_bloque`) | `email` |

### À créer dans BotPanel (une fois)

Crée trois notifications avec ces slugs (ou change les slugs dans `.env`) :

| Slug | Exemple de titre | Exemple de message |
|---|---|---|
| `acces_demande` | `🔔 Nouvelle demande d'accès` | `{var:email} demande un accès. Valide-la dans les Paramètres.` |
| `acces_valide` | `✅ Accès validé` | `Le compte {var:email} a été validé.` |
| `acces_bloque` | `⛔ Accès bloqué` | `Le compte {var:email} a été bloqué.` |

---

## Ajouter une notification dans ton projet

1. Crée la notification dans BotPanel, note son slug.
2. Appelle `notify("ton_slug", cle="valeur", ...)` là où l'événement se produit.

```python
from panel.notify import notify

def apres_une_action():
    notify("action_faite", user="jean", montant="42 €")
```

Dans le template BotPanel : `Titre : {var:user} a payé {var:montant}`.

---

## Contrat de l'API (rappel, côté BotPanel)

```
POST {BOTPANEL_URL}/api/notify
Content-Type: application/json

{ "id": "<slug>", "vars": { "nom": "valeur" } }   // vars optionnel
```

| Code | Signification |
|---|---|
| `200` | Envoyée — `{"status": "sent", "message_id": "..."}` |
| `404` | Slug inconnu / échec d'envoi (channel introuvable) |
| `422` | JSON invalide (champ `id` manquant) |

- Route **toujours ouverte** (pas de token) → garde BotPanel sur ton **LAN** ou
  derrière un tunnel/VPN.
- Syntaxe des variables : `{var:nom}` (vide si non fourni) ou `{var:nom|défaut}`.
- Les `{var:...}` marchent dans le titre, le message, les champs, le footer, la
  miniature et la grande image.

Voir la doc complète : `docs/API.md` du dépôt BotPanel.
