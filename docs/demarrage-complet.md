# Démarrage complet — de zéro au hub avec login unique

> Parcours pas-à-pas : installer le hub, le configurer, le publier sur
> `super-nono.cc`, puis brancher le **login unique (SSO)** Cloudflare.

---

## Partie 1 — Installer le hub (≈ 5 min)

Sur le **shell de ton node Proxmox**, lance (mets ton e-mail Google) :

```bash
ADMIN_EMAIL=ton.email@gmail.com bash -c "$(curl -fsSL https://raw.githubusercontent.com/SuperNon0/site/main/install.sh)"
```

> Ajoute `CT_STORAGE=local-zfs` devant si ton stockage n'est pas `local-lvm`.

À la fin, note ce qui s'affiche :
- **URL** : `http://IP_DU_HUB:8000`
- **Mot de passe SUPER-ADMIN** (login local) — **note-le**.

## Partie 2 — Première connexion + remplir le hub

1. Ouvre `http://IP_DU_HUB:8000`.
2. Connecte-toi avec le **mot de passe super-admin**.
3. En haut : **« Gérer »** → tu peux :
   - **+ Catégorie**, **+ Section**, **+App**, **+Raccourci** ;
   - pour chaque tuile : **icône** (Emoji / Logo uploadé / MDI), nom, lien, couleur ;
   - réordonner (↑↓), modifier (✎), supprimer (✕).
4. **Paramètres** (en haut) → changer le mot de passe, gérer les comptes, régler Cloudflare.

*(Tes 9 apps sont déjà pré-remplies : tu n'as qu'à corriger les liens.)*

## Partie 3 — Publier le hub sur `super-nono.cc`

Dans ton **tunnel Cloudflare** (le conteneur qui gère `cloudflared`), ajoute une
route :

```
super-nono.cc   →   http://IP_DU_HUB:8000
```

Recharge → `https://super-nono.cc` doit afficher le hub.

---

## Partie 4 — Le login unique (SSO) Cloudflare

### 4.1 Fournisseur d'identité (Google)
Zero Trust (`one.dash.cloudflare.com`) → **Settings → Authentication → Login
methods → Add new → Google**.
- OAuth client Google (Google Cloud Console) ; redirect URI :
  `https://TONÉQUIPE.cloudflareaccess.com/cdn-cgi/access/callback`
- *(Alternative test rapide : « One-time PIN », code par e-mail, zéro config.)*

### 4.2 Application Access (couvre tout)
Access → **Applications → Add → Self-hosted** :
- domaines : **`super-nono.cc`** ET **`*.super-nono.cc`**
- Identity providers : **Google**.

### 4.3 Policy (qui a le droit)
Add a policy → **Allow** → **Include : Emails** → tes e-mails autorisés → Save.

### 4.4 Récupérer Équipe + AUD
- **Équipe** = `TONÉQUIPE` (de `TONÉQUIPE.cloudflareaccess.com`).
- **AUD** = Access → ton app → **Overview → Application Audience (AUD) Tag**.

### 4.5 Brancher au hub
Hub → **Paramètres → Cloudflare / Accès** → colle **Équipe** + **AUD**, coche
**Vérifier le JWT**, Enregistre.

## Partie 5 — Tester

1. `https://super-nono.cc` en navigation privée → **login Google** → le hub.
2. `https://fuel.super-nono.cc` → **déjà connecté** (SSO). 🎉

## Partie 6 — Ajouter un membre

1. Son e-mail dans la **policy Cloudflare** (4.3).
2. Sa 1ʳᵉ connexion → il passe **en attente** dans le hub (**Paramètres →
   Comptes**) → tu **valides** (+ notif BotPanel).

## Partie 7 — Alléger les logins des apps (optionnel)

Pour que `fuel`, `recipe`… n'aient plus leur propre login mais lisent l'e-mail
Cloudflare : transmets à ton dev le doc
[`connexion-cloudflare-apps.md`](connexion-cloudflare-apps.md). Chaque app garde
juste **un mot de passe admin local** pour l'accès LAN.

## Sécurité — à ne pas oublier

- `CF_VERIFY_JWT=true` une fois le tunnel branché (fait en 4.5).
- Idéalement, un **pare-feu** pour que le hub/les apps n'acceptent que le
  conteneur tunnel (sinon joignables en LAN sans auth).

---

**Récap** : installer (P1) → remplir (P2) → publier (P3) → SSO Cloudflare (P4) →
tester (P5) → membres (P6) → apps (P7).
