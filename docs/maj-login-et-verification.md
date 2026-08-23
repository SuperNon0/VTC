# Mise à jour du système de login + vérification (à lire par le dev)

> À transmettre au développeur qui maintient une version de `site-base` avec du
> contenu déjà en place. Ce document décrit **le système de login tel qu'il est
> maintenant**, **ce qui a changé** (donc à ne plus faire), **comment garder ton
> contenu**, et **comment vérifier** que la connexion Cloudflare fonctionne.

---

## 1. Ce que fait le login aujourd'hui

Deux couches, **inchangées dans le principe** :

- **Cloudflare Zero Trust** = portier : il authentifie la personne (Google) et
  transmet un **e-mail vérifié** + un **JWT signé** à chaque requête.
- **L'application (Flask)** = comptes, rôles, cycle de vie.

Comportement selon le canal d'entrée (`panel/routes/auth_routes.py → gateway`) :

| Canal | Ce qui s'affiche |
|---|---|
| **Domaine derrière Cloudflare** (JWT présent) | connexion automatique par e-mail Google (SSO) |
| **Accès local / IP** (pas de JWT) | **login local par mot de passe** (super-admin, secours LAN) |

Rôles : `super_admin` (toi, gère tout, login local possible) et `membre`.
Cycle d'un compte : `pending → actif / refused / bloque`.

---

## 2. Ce qui a CHANGÉ (à mettre à jour / à ne plus faire)

1. **La config Cloudflare se règle dans l'UI, pas seulement dans le `.env`.**
   - Écran **Paramètres → « Cloudflare / Accès »** : équipe, AUD, case « Vérifier
     le JWT ». Stocké en base (table `app_settings`), **prioritaire** sur le `.env`.
   - Le code lit la config via `panel/settings.py → cf_config()`.

2. **Le champ « Équipe » = le NOM d'équipe seul** (ex. `super-nono`), **pas** le
   domaine complet. Mettre `super-nono.cloudflareaccess.com` provoquait un doublon
   `…cloudflareaccess.com.cloudflareaccess.com` → échec SSL de récupération des
   clés. Le code **normalise** désormais (retire `https://`, un `.cloudflareaccess.com`
   final, les `/`), mais garde l'habitude du **nom seul**.

3. **`/login` accepte GET** (redirige vers `/gateway`). Avant, un accès direct en
   GET donnait un **405 Method Not Allowed**. Ne pas remettre `methods=["POST"]` seul.

4. **La page de login se centre correctement même avec un message d'erreur.**
   `.login-page` est en `flex-direction: column` (le flash se met **au-dessus**
   de la carte, plus à côté). Ne pas retirer.

5. **Rattachement de l'e-mail super-admin.** Au démarrage, si un super-admin
   existe sans e-mail et que `SUPERADMIN_EMAIL` est renseigné, l'e-mail lui est
   **rattaché automatiquement** (`panel/db.py → _seed_superadmin`). Sert à être
   reconnu comme super-admin quand on arrive par Google.

6. **Mise à jour depuis l'UI** (Paramètres → « Mise à jour ») : le service fait
   lui-même `git pull` + install et se recharge par **SIGHUP à gunicorn** (pas de
   `sudo`). Ne plus s'appuyer sur un helper root.

> ⚠️ Ce qu'on **ne touche pas** (contrat, cf. `CLAUDE.md`) : le thème
> `panel/static/style.css`, la structure des écrans d'auth, et la **sécurité**
> (vérif JWT + `aud`, dernier super-admin indestructible, `/api/*` en `no-store`).

---

## 3. Comment garder / retrouver TON contenu

Le login, le thème et la gestion des comptes sont la **fondation**. **Ton
contenu métier** vit dans **deux endroits seulement** :

- **`panel/routes/main.py`** — tes routes applicatives.
- **`panel/templates/dashboard.html`** (+ tes templates) — tes écrans.
- **Tes tables** dans la base (ajoutées dans `panel/db.py`), lues via tes routes.

**Marche à suivre pour te mettre à jour sans perdre ton contenu :**

1. Récupère les fichiers **de fondation** de la version à jour :
   `panel/auth.py`, `panel/settings.py`, `panel/db.py` (schéma), `panel/config.py`,
   `panel/routes/auth_routes.py`, `panel/routes/accounts_routes.py`,
   `panel/static/style.css`, et les templates d'auth (`login/attente/refus/bloque/
   demande/comptes/parametres/base/oubli`).
2. **Conserve tes** `routes/main.py`, tes templates métier et tes tables.
3. Vérifie que ton `main.py` protège bien tes routes avec `@login_required` (et
   `@super_admin_required` pour l'admin), importés depuis `panel/auth.py`.
4. Si tes données doivent être **par utilisateur**, filtre-les par le **compte
   effectif** (voir impersonation) — sinon elles restent partagées.

---

## 4. La vérification à ajouter (diagnostic de connexion)

Objectif : quand on est connecté sur un site, aller dans **Paramètres** et voir
**si Cloudflare est bien branché**, **quel e-mail est détecté**, et **le résultat
de la vérification du JWT** (avec la raison de l'échec).

### 4.1 Fonction (dans `panel/auth.py`)

```python
def cf_diagnostic() -> dict:
    from .settings import cf_config
    cfg = cf_config()
    header_email = request.headers.get("Cf-Access-Authenticated-User-Email")
    token = (request.headers.get("Cf-Access-Jwt-Assertion")
             or request.cookies.get("CF_Authorization"))
    d = {"team": cfg["team"], "aud": cfg["aud"], "verify": cfg["verify"],
         "header_email": header_email or "", "has_token": bool(token),
         "jwt_status": "non testé", "jwt_email": "", "jwt_error": ""}
    if not token:
        d["jwt_error"] = "Aucun jeton Cloudflare reçu (accès local, ou tunnel qui ne le transmet pas)."
        return d
    if not cfg["team"] or not cfg["aud"]:
        d["jwt_error"] = "Équipe et/ou AUD non renseignés."
        return d
    try:
        client = _get_jwk_client(cfg["team"])           # PyJWKClient mis en cache par équipe
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=cfg["aud"],
                            issuer=f"https://{cfg['team']}.cloudflareaccess.com")
        d["jwt_status"] = "OK ✓"; d["jwt_email"] = claims.get("email", "")
    except Exception as exc:
        d["jwt_status"] = "échec ✗"; d["jwt_error"] = str(exc)
    return d
```

### 4.2 Affichage (écran Paramètres, super-admin)

Passer `diag=cf_diagnostic()` au template et afficher : **jeton reçu (oui/non)**,
**en-tête e-mail**, **équipe / AUD** configurés, **résultat vérif JWT** + le
**détail** de l'erreur. C'est ce détail qui dit exactement quoi corriger.

### 4.3 Comment lire le diagnostic

| Ce que tu vois | Ce que ça veut dire |
|---|---|
| Jeton reçu = **non** (par le domaine) | Cloudflare Access n'est pas **devant** ce domaine |
| `échec ✗` + « certificate … .cloudflareaccess.com.cloudflareaccess.com » | Équipe = domaine complet → mets le **nom seul** |
| `échec ✗` + « audience » | **AUD** ne correspond pas à l'app Access |
| `OK ✓` + ton e-mail | tout est bon → tu peux cocher « Vérifier le JWT » |

---

## 5. Checklist de vérification (à passer après mise à jour)

- [ ] Login **local** (par IP) avec le mot de passe super-admin → OK.
- [ ] Accès par le **domaine** → login **Google**, puis dashboard (SSO).
- [ ] **Paramètres → Diagnostic** montre `OK ✓` + le bon e-mail.
- [ ] **Changer le mot de passe** (Paramètres) fonctionne.
- [ ] **Reset CLI** : `sudo bash deploy/reset_admin.sh` (ou `python -m panel.reset_admin`).
- [ ] **Comptes** : valider / refuser / bloquer / supprimer / « voir en tant que ».
- [ ] `/api/*` renvoie `Cache-Control: no-store`.
- [ ] Un accès direct à `/login` en GET **redirige** (pas de 405).

---

En résumé pour le dev : **récupère la fondation à jour** (auth, settings, db,
routes d'auth, thème, templates d'auth), **garde ton `main.py`, tes templates
métier et tes tables**, **règle Cloudflare dans les Paramètres** (nom d'équipe
seul), et **ajoute le diagnostic** pour vérifier la connexion d'un coup d'œil.
