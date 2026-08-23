# Brancher une app sur le login centralisé (Cloudflare Zero Trust)

> Doc à transmettre au développeur d'une app (fuel, recipe, botpanel…). Objectif :
> **supprimer le système de login propre à l'app** et faire en sorte qu'elle
> **récupère l'utilisateur connecté depuis Cloudflare**, avec un **seul login de
> secours** (mot de passe admin) pour l'accès local.

## 1. Le principe

L'authentification est **centralisée sur Cloudflare Zero Trust** (SSO) :

- **Cloudflare** authentifie la personne (login Google) **avant** qu'elle
  atteigne l'app, et transmet son **e-mail vérifié** à chaque requête.
- **L'app** ne gère plus de comptes/mots de passe : elle **fait confiance à cet
  e-mail** pour savoir qui est connecté.

Résultat : **un seul login pour tous les sites**, et l'app n'a plus son propre écran de connexion — sauf un **fallback local** (voir §4).

## 2. Ce qu'il faut RETIRER de l'app

- L'écran de **connexion / inscription** propre à l'app.
- La **base d'utilisateurs / mots de passe** interne (ou la garder en lecture
  seule le temps de la migration, mais ne plus l'utiliser pour authentifier).
- La **récupération de mot de passe**.

## 3. Comment récupérer l'utilisateur (à AJOUTER)

À chaque requête, Cloudflare envoie deux choses :

| En-tête | Contenu |
|---|---|
| `Cf-Access-Authenticated-User-Email` | l'e-mail de la personne (pratique, mais **falsifiable** — voir sécurité) |
| `Cf-Access-Jwt-Assertion` | un **jeton signé (JWT)** prouvant l'identité (c'est LUI la vraie preuve) |

> Le JWT est aussi présent dans le cookie `CF_Authorization`.

### ⚠️ Sécurité — ne PAS se fier à l'en-tête e-mail seul

N'importe qui pouvant joindre l'app **sans passer par Cloudflare** (ex. en LAN
sur son IP) peut **forger** l'en-tête `Cf-Access-Authenticated-User-Email`. Donc :

**Il faut VÉRIFIER le JWT** contre les clés publiques de l'équipe Cloudflare, et
contrôler l'`aud`. Deux valeurs à demander au propriétaire :

- **Équipe Cloudflare** → clés publiques :
  `https://<EQUIPE>.cloudflareaccess.com/cdn-cgi/access/certs`
- **AUD** (Application Audience tag) de l'application Access.

Vérification du JWT :
1. récupérer le JWT (`Cf-Access-Jwt-Assertion` ou cookie `CF_Authorization`) ;
2. valider la **signature** (RS256) avec les clés publiques ci-dessus ;
3. contrôler `aud == <AUD>` et `iss == https://<EQUIPE>.cloudflareaccess.com` ;
4. l'e-mail de confiance = le champ `email` **du JWT** (pas de l'en-tête).

En complément, **fermer l'accès direct** (pare-feu : l'app n'accepte que le
conteneur tunnel Cloudflare) pour qu'aucune requête ne contourne Cloudflare.

## 4. Le SEUL login qui reste : le fallback local (LAN)

Quand il n'y a **pas** de JWT Cloudflare (accès direct en local, sans tunnel),
l'app affiche un **login par mot de passe administrateur** :

- un **unique mot de passe admin** (le même sur toutes les apps, fourni par le
  propriétaire) ;
- utilisé **uniquement** pour l'accès local ; en accès normal (via Cloudflare),
  ce login ne s'affiche jamais.

### Logique de connexion (résumé)

```
À chaque requête :
  jwt = lire (Cf-Access-Jwt-Assertion | cookie CF_Authorization)
  SI jwt valide (signature + aud + iss) :
      utilisateur = email du jwt          # connecté via Cloudflare, aucun login
  SINON SI session locale active :
      utilisateur = admin local
  SINON :
      afficher le login local (mot de passe admin)   # fallback LAN uniquement
```

## 5. Valeurs à demander au propriétaire

| Valeur | Exemple | Où |
|---|---|---|
| Équipe Cloudflare | `mon-equipe` | Zero Trust → Settings |
| AUD de l'app Access | `a1b2c3…` | Access → l'app → Overview |
| Mot de passe admin local | (secret) | fixé par le propriétaire, **le même partout** |

Ces valeurs vont dans la **config de l'app** (variables d'environnement / `.env`),
jamais en dur dans le code, jamais sur un dépôt public.

## 6. Exemple (Python / Flask — transposable à tout langage)

```python
import os, jwt                      # PyJWT[crypto]
from jwt import PyJWKClient
from flask import request, session, redirect, render_template

TEAM = os.environ["CF_TEAM"]        # ex: mon-equipe
AUD  = os.environ["CF_AUD"]
ADMIN_PWD = os.environ["ADMIN_PASSWORD"]
_jwks = PyJWKClient(f"https://{TEAM}.cloudflareaccess.com/cdn-cgi/access/certs")

def utilisateur_courant():
    token = (request.headers.get("Cf-Access-Jwt-Assertion")
             or request.cookies.get("CF_Authorization"))
    if token:
        try:
            key = _jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"],
                                audience=AUD,
                                issuer=f"https://{TEAM}.cloudflareaccess.com")
            return {"email": claims["email"], "via": "cloudflare"}
        except Exception:
            pass                       # jeton absent/invalide → on tente le local
    if session.get("admin_local"):
        return {"email": "admin (local)", "via": "local"}
    return None                        # pas connecté → login local

# Login local (fallback LAN, mot de passe admin unique)
def login_local(password):
    if password == ADMIN_PWD:
        session["admin_local"] = True
        return True
    return False
```

> Le fichier `panel/auth.py` du **site-base** est une **implémentation de
> référence** complète de cette logique (JWT Cloudflare + login local) : à
> reprendre / adapter.

## 7. Ce que le propriétaire fait de son côté (aucune action pour le dev)

- Ajouter le sous-domaine de l'app à la **policy Cloudflare Access** (`*.super-nono.cc`).
- Fournir au dev : équipe, AUD, mot de passe admin.
- (Recommandé) pare-feu pour que l'app ne soit joignable **que** via Cloudflare.

---

En résumé pour le dev : **retirer le login de l'app**, **lire l'e-mail depuis le
JWT Cloudflare vérifié**, et **garder un seul login local par mot de passe admin**
pour l'accès en LAN. Rien d'autre.
