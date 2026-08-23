# Tuto — Login unique (SSO) avec Cloudflare Zero Trust

> Objectif : **une seule connexion** (Google) qui ouvre **tous** tes sous-domaines
> `*.super-nono.cc` (le hub + fuel, recipe, botpanel…), et le hub qui reconnaît
> automatiquement qui est connecté.

## 0. Pré-requis

- Le domaine `super-nono.cc` est géré par **Cloudflare**.
- Ton **tunnel `cloudflared`** route déjà tes sous-domaines vers tes conteneurs.
- Tu as accès à **Cloudflare Zero Trust** : <https://one.dash.cloudflare.com>
  (si c'est la 1ʳᵉ fois, choisis un **team name** → ça donne `TONÉQUIPE.cloudflareaccess.com`).

## 1. Ajouter le login Google (fournisseur d'identité)

Zero Trust → **Settings → Authentication → Login methods → Add new**.

- Choisis **Google** (recommandé). Il faut un « OAuth client » Google :
  - Google Cloud Console → *APIs & Services → Credentials → Create OAuth client ID → Web application*.
  - **Authorized redirect URI** : `https://TONÉQUIPE.cloudflareaccess.com/cdn-cgi/access/callback`
  - Récupère **Client ID** + **Client secret**, colle-les dans Cloudflare, **Save**.
- Clique **Test** pour vérifier.

> ⚡ Alternative sans rien configurer : **One-time PIN** (code envoyé par e-mail).
> Pratique pour tester tout de suite ; tu ajouteras Google ensuite.

## 2. Créer l'application Access (couvre tous les sous-domaines)

Zero Trust → **Access → Applications → Add an application → Self-hosted**.

- **Application name** : `super-nono`
- **Session duration** : `24h` (ou plus).
- **Application domain** — ajoute **deux entrées** :
  - `super-nono.cc`
  - `*.super-nono.cc`  ← le wildcard couvre `fuel.`, `recipe.`, etc. d'un coup
- **Identity providers** : coche **Google** (et/ou One-time PIN).
- **Next**.

## 3. Créer la policy (qui a le droit d'entrer)

Dans l'application, **Add a policy** :

- **Policy name** : `Autorisés`
- **Action** : **Allow**
- **Include** : **Emails** → liste les e-mails Google autorisés
  (ou *Emails ending in* pour tout un domaine).
- **Save**. Puis **Save application**.

> Pour **ajouter quelqu'un plus tard** : reviens ici, ajoute son e-mail dans la policy.

## 4. Récupérer l'ÉQUIPE + l'AUD

- **Équipe** : le `TONÉQUIPE` de `TONÉQUIPE.cloudflareaccess.com`
  (Zero Trust → **Settings → Custom Pages**, ou le nom choisi au début).
- **AUD** : Access → **ton application → Overview** → **Application Audience (AUD) Tag** (copie la longue chaîne).

## 5. Brancher au hub

Ouvre le hub → **Paramètres → Cloudflare / Accès** :

- **Équipe Cloudflare** : `TONÉQUIPE`
- **AUD** : la chaîne copiée
- coche **Vérifier le JWT Cloudflare**
- **Enregistrer**.

> Astuce : que ton compte Google soit reconnu **direct comme super-admin**,
> déploie le hub avec ton e-mail (`ADMIN_EMAIL=toi@gmail.com bash -c "$(curl …)"`),
> ou mets `SUPERADMIN_EMAIL=` dans `/opt/site-base/.env` puis
> `systemctl restart site-base`.

## 6. Tester

1. Ouvre `https://super-nono.cc` en navigation privée → tu es **redirigé vers le
   login Cloudflare** → connexion Google → tu arrives sur le hub.
2. Ouvre `https://fuel.super-nono.cc` → **déjà connecté** (SSO). 🎉

## 7. Ajouter un membre

1. Ajoute son e-mail dans la **policy Cloudflare** (étape 3).
2. À sa 1ʳᵉ connexion, il apparaît **en attente** dans le hub
   (**Paramètres → Comptes**) → tu **valides**. Tu reçois aussi une **notif BotPanel**.

## 8. (Recommandé) Verrouiller l'accès direct

Comme le hub/les apps restent joignables en LAN par IP, pense à :
- passer `CF_VERIFY_JWT=true` (fait à l'étape 5) — un en-tête forgé sans jeton
  signé est rejeté ;
- idéalement, un **pare-feu** pour que les apps n'acceptent que le conteneur tunnel.

---

**Résumé** : Google comme login → 1 app Access sur `*.super-nono.cc` → 1 policy
avec les e-mails → équipe + AUD dans les Paramètres du hub → un seul login pour tout.
