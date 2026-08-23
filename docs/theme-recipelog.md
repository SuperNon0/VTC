# Cahier des charges — Système de thème « RecipeLog »

> Objectif : reproduire un site avec **exactement le même thème visuel** que
> RecipeLog (identité sombre, accents dorés, typographie serif/mono).
> Ce document est autonome : tout le code nécessaire est fourni, prêt à copier.

---

## 1. Identité visuelle en une phrase

Interface **sombre** (dark-only), élégante et « éditoriale » : fond anthracite,
**accent doré** (`#e8c547`), titres en **serif display** (DM Serif Display) et
tout le reste en **monospace** (DM Mono). Coins arrondis, cartes discrètes,
typographie en petites capitales espacées pour les labels.

---

## 2. Stack technique de référence

| Élément | Version / choix |
|---|---|
| Framework | Next.js 15 (App Router) |
| React | 19 |
| CSS | **Tailwind CSS v4** (`@import "tailwindcss"` + bloc `@theme`) |
| PostCSS | plugin `@tailwindcss/postcss` |
| Police serif | **DM Serif Display** (Google Fonts, normal + italique) |
| Police mono | **DM Mono** (Google Fonts, poids 300 / 400 / 500) |
| Mode couleur | `color-scheme: dark` (pas de thème clair) |

> Le thème ne dépend PAS de Next/React : les tokens et classes ci-dessous sont
> du CSS pur, réutilisables dans n'importe quel projet (Vite, Astro, HTML nu…).
> Seule la partie « layout » (§7) utilise des composants React à titre d'exemple.

---

## 3. Jetons de design (design tokens)

### 3.1 Couleurs

| Token CSS | Hex | Rôle |
|---|---|---|
| `--bg` | `#0e0f11` | Fond global de la page (quasi noir) |
| `--surface` | `#16181c` | Surfaces surélevées (header, menus déroulants) |
| `--card` | `#1c1f25` | Fond des cartes / panneaux |
| `--border` | `#2a2d35` | Bordures, séparateurs |
| `--accent` | `#e8c547` | **Accent principal — doré** (titres, CTA, actif) |
| `--accent-2` | `#4fc3a1` | Accent secondaire — vert menthe (coefficients, succès) |
| `--accent-3` | `#e87c47` | Accent tertiaire — orange |
| `--pending` | `#a78bfa` | Violet — états « en attente » / bouton flottant (FAB) |
| `--danger` | `#e85c47` | Rouge — suppression, erreurs |
| `--text` | `#f0ede6` | Texte principal (blanc cassé chaud) |
| `--muted` | `#6b6f7a` | Texte secondaire, labels, placeholders |

Variantes d'accent avec transparence utilisées dans les composants :
- Doré fond léger : `rgba(232, 197, 71, 0.10)` à `0.20`
- Violet fond léger : `rgba(167, 139, 250, 0.15)` à `0.30`
- Rouge fond léger : `rgba(232, 92, 71, 0.08)` à `0.20`
- Survol blanc discret : `rgba(255, 255, 255, 0.03)` à `0.06`

### 3.2 Typographie

| Token | Valeur |
|---|---|
| `--font-serif` | `"DM Serif Display", Georgia, serif` |
| `--font-mono` | `"DM Mono", ui-monospace, SFMono-Regular, Menlo, monospace` |

- **Serif** = titres, valeurs numériques mises en avant, logo.
- **Mono** = corps de texte, labels, boutons, navigation, champs.
- Taille de base du corps : **0,85 rem**, interligne **1,5**.
- Lissage : `-webkit-font-smoothing: antialiased`.

### 3.3 Rayons d'arrondi

| Token | Valeur | Usage |
|---|---|---|
| `--radius-sm` | `8px` | Boutons, champs, tags |
| `--radius-md` | `12px` | Cartes |
| `--radius-lg` | `20px` | FAB, grandes surfaces / modales |

---

## 4. Fichier `globals.css` complet (à copier tel quel)

> C'est le cœur du thème. Copie ce fichier entier. Il contient : import Tailwind,
> déclaration des tokens (deux fois : `@theme` pour Tailwind + `:root` pour le CSS
> direct), reset léger, styles de base et **toute la bibliothèque de classes `fl-*`**.

```css
@import "tailwindcss";

/* ─────────────────────────────────────────────
   Design system — tokens
   ───────────────────────────────────────────── */

@theme {
  --color-bg: #0e0f11;
  --color-surface: #16181c;
  --color-card: #1c1f25;
  --color-border: #2a2d35;

  --color-accent: #e8c547;
  --color-accent-2: #4fc3a1;
  --color-accent-3: #e87c47;
  --color-pending: #a78bfa;
  --color-danger: #e85c47;

  --color-text: #f0ede6;
  --color-muted: #6b6f7a;

  --font-serif: "DM Serif Display", Georgia, serif;
  --font-mono: "DM Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 20px;
}

:root {
  --bg: #0e0f11;
  --surface: #16181c;
  --card: #1c1f25;
  --border: #2a2d35;
  --accent: #e8c547;
  --accent-2: #4fc3a1;
  --accent-3: #e87c47;
  --pending: #a78bfa;
  --danger: #e85c47;
  --text: #f0ede6;
  --muted: #6b6f7a;

  color-scheme: dark;
}

* {
  box-sizing: border-box;
}

html,
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-mono);
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100%;
}

body {
  font-size: 0.85rem;
  line-height: 1.5;
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
}

button {
  font-family: inherit;
  cursor: pointer;
}

input,
textarea,
select {
  font-family: inherit;
  color: inherit;
}

a {
  color: inherit;
  text-decoration: none;
}

/* ─────────────────────────────────────────────
   Classes utilitaires composants
   ───────────────────────────────────────────── */

.fl-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.3rem;
}

.fl-label {
  font-family: var(--font-mono);
  font-size: 0.63rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted);
  font-weight: 400;
}

.fl-input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 0.85rem;
  padding: 0.6rem 0.85rem;
  width: 100%;
  transition: border-color 120ms ease;
}

.fl-input:focus {
  outline: none;
  border-color: var(--accent);
}

.fl-input::placeholder {
  color: var(--muted);
}

.fl-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  font-family: var(--font-mono);
  font-size: 0.76rem;
  letter-spacing: 0.04em;
  padding: 0.65rem 1.1rem;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: background-color 120ms ease, border-color 120ms ease,
    color 120ms ease, transform 60ms ease;
  cursor: pointer;
  white-space: nowrap;
}

.fl-btn:active {
  transform: translateY(1px);
}

.fl-btn-primary {
  background: var(--accent);
  color: #0e0f11;
  font-weight: 700;
}
.fl-btn-primary:hover {
  background: #f0d25a;
}

.fl-btn-secondary {
  background: transparent;
  color: var(--muted);
  border-color: var(--border);
}
.fl-btn-secondary:hover {
  color: var(--text);
  border-color: var(--muted);
}

.fl-btn-pending {
  background: rgba(167, 139, 250, 0.15);
  color: var(--pending);
  border-color: rgba(167, 139, 250, 0.3);
}
.fl-btn-pending:hover {
  background: rgba(167, 139, 250, 0.25);
}

.fl-btn-danger {
  background: rgba(232, 92, 71, 0.08);
  color: var(--danger);
  border-color: rgba(232, 92, 71, 0.2);
}
.fl-btn-danger:hover {
  background: rgba(232, 92, 71, 0.18);
}

.fl-btn-edit {
  background: rgba(232, 197, 71, 0.1);
  color: var(--accent);
  border-color: rgba(232, 197, 71, 0.2);
}
.fl-btn-edit:hover {
  background: rgba(232, 197, 71, 0.2);
}

.fl-tag {
  display: inline-flex;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.2rem 0.55rem;
  border-radius: 6px;
  background: rgba(107, 111, 122, 0.15);
  color: var(--muted);
  border: 1px solid var(--border);
}

.fl-title-serif {
  font-family: var(--font-serif);
  font-weight: 400;
  color: var(--accent);
  line-height: 1.15;
}

.fl-value-serif {
  font-family: var(--font-serif);
  font-weight: 400;
  line-height: 1;
  color: var(--accent);
}

.fl-nav-item {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted);
  padding: 0 1.6rem;
  height: 54px;
  border-bottom: 3px solid transparent;
  white-space: nowrap;
  transition: color 120ms ease, border-color 120ms ease;
  display: flex;
  align-items: center;
}
.fl-nav-item:hover {
  color: var(--text);
}
.fl-nav-item[aria-current="page"] {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
}

/* Pill nav */
.fl-nav-pill:hover {
  background: rgba(255, 255, 255, 0.06) !important;
  color: var(--text) !important;
}
.fl-nav-pill[aria-current="page"]:hover {
  background: rgba(232, 197, 71, 0.18) !important;
  color: var(--accent) !important;
}
.fl-nav-pill:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

/* Scrollbars sobres */
.fl-scroll::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.fl-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.fl-scroll::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}
.fl-scroll-hidden::-webkit-scrollbar {
  display: none;
}
.fl-scroll-hidden {
  scrollbar-width: none;
}
```

---

## 5. Bibliothèque de composants (classes `fl-*`)

Récapitulatif de ce que fournit le thème, avec le HTML type.

| Classe | Rôle | Exemple HTML |
|---|---|---|
| `fl-card` | Carte / panneau | `<div class="fl-card">…</div>` |
| `fl-label` | Petit label en capitales espacées | `<span class="fl-label">Masse totale</span>` |
| `fl-input` | Champ texte / textarea / select | `<input class="fl-input" />` |
| `fl-btn` | Base bouton (à combiner) | `<button class="fl-btn fl-btn-primary">…</button>` |
| `fl-btn-primary` | Bouton d'action doré | CTA principal |
| `fl-btn-secondary` | Bouton discret (contour) | action secondaire |
| `fl-btn-pending` | Bouton violet (en attente) | verrouillage, statut |
| `fl-btn-danger` | Bouton rouge | suppression |
| `fl-btn-edit` | Bouton doré léger | édition / ajustement |
| `fl-tag` | Étiquette / chip | `<span class="fl-tag">#tag</span>` |
| `fl-title-serif` | Titre serif doré | `<h1 class="fl-title-serif">…</h1>` |
| `fl-value-serif` | Grande valeur numérique serif | `<span class="fl-value-serif">1,05 kg</span>` |
| `fl-nav-item` | Onglet de navigation (soulignement) | header desktop |
| `fl-nav-pill` | Onglet « pilule » (fond arrondi) | navigation mobile |
| `fl-scroll` | Scrollbar fine stylée | conteneurs scrollables |
| `fl-scroll-hidden` | Masque la scrollbar | carrousels |

**Règles typographiques implicites**
- Les titres emploient TOUJOURS `fl-title-serif` (serif doré), la taille est fixée
  en style inline selon le contexte (ex. `1.6rem` page, `1.15rem` carte, `2rem`
  fiche recette).
- Les labels de champ / métadonnées emploient `fl-label` (capitales, 0,63 rem,
  `letter-spacing: 0.07em`, couleur `--muted`).
- Les valeurs chiffrées mises en avant emploient `fl-value-serif`.

---

## 6. Styles de base (résumé)

- **Fond** `--bg`, **texte** `--text`, **police par défaut** = mono.
- `overflow-x: hidden` sur `html, body` (empêche tout débordement horizontal).
- Respect des encoches mobiles via `env(safe-area-inset-*)` en padding haut/bas.
- Liens : héritent la couleur, sans soulignement.
- Boutons : `cursor: pointer`, police héritée.
- Champs : police + couleur héritées.

---

## 7. Structure de mise en page (layout)

### 7.1 Squelette de page

- `<header>` **sticky** en haut (`position: sticky; top: 0; z-index: 40`),
  fond `--surface`, bordure basse `1px solid --border`.
- `<main>` centré : largeur max **`max-w-5xl`** (~64rem), padding horizontal
  `1rem`, padding vertical `1.5rem`, marge basse importante (`pb-28`) pour
  laisser la place au bouton flottant.

Exemple (React/Next, mais transposable) :

```tsx
<html lang="fr">
  <head>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
    <link
      href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@300;400;500&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <header className="sticky top-0 z-40" style={{ background: "var(--surface)" }}>
      <AppNav />
    </header>
    <main className="max-w-5xl mx-auto px-4 py-6 pb-28">{children}</main>
  </body>
</html>
```

Meta / viewport recommandés :
```
themeColor = "#0e0f11"
viewport   = width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover
```

### 7.2 Barre de navigation (logo + « pilules »)

- Hauteur **56px**, largeur max `max-w-5xl`, centrée.
- **Logo** en serif : première moitié en doré, seconde en italique couleur texte,
  suivi d'un petit badge de version en mono (`0.55rem`, fond `rgba(255,255,255,0.04)`,
  arrondi 4px). Exemple : `recipe` (doré) + `log` (italique clair) + `v1.3`.
- **Navigation** : conteneur `background: rgba(255,255,255,0.03)`, `border-radius: 10px`,
  padding `0.25rem`. Chaque onglet = « pilule » :
  - `padding: 0.45rem 0.85rem`, `border-radius: 8px`, `font-size: 0.72rem`, mono.
  - Inactif : couleur `--muted`, fond transparent.
  - Actif (`aria-current="page"`) : couleur `--accent`, fond `rgba(232,197,71,0.12)`,
    `font-weight: 600`.
  - Icône emoji à gauche, libellé masqué en dessous de `sm` (icône seule sur mobile).

Onglets de référence : 📖 Recettes · ★ Favoris · 📚 Cahiers · 🛒 Courses · ⚙ Réglages.

### 7.3 Bouton d'action flottant (FAB)

- Fixé en bas à droite : `bottom: calc(1.5rem + env(safe-area-inset-bottom))`,
  `right: 1.2rem`.
- Carré arrondi **64×64px**, `border-radius: 20px`, fond **`--pending`** (violet),
  texte `#0e0f11`, `font-size: 2rem`, `font-weight: 700`.
- Ombre : `0 4px 16px rgba(167, 139, 250, 0.35)`.

```tsx
<a href="…" style={{
  position: "fixed",
  bottom: "calc(1.5rem + env(safe-area-inset-bottom))",
  right: "1.2rem",
  width: 64, height: 64,
  background: "var(--pending)", color: "#0e0f11",
  borderRadius: 20, fontSize: "2rem", fontWeight: 700,
  boxShadow: "0 4px 16px rgba(167, 139, 250, 0.35)",
  display: "flex", alignItems: "center", justifyContent: "center",
}}>+</a>
```

### 7.4 État vide (empty state)

Carte centrée : `fl-card`, texte centré, padding vertical généreux (`py-14`),
titre `fl-title-serif` (~`1.35rem`), description en `--muted` (largeur max `md`),
et un CTA `fl-btn fl-btn-primary` optionnel.

---

## 8. Grilles & espacements types (conventions Tailwind observées)

- Grilles de cartes : `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4`.
- Grille de « dossiers » compacts : `grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2`.
- En-têtes de page : `flex items-baseline justify-between mb-5 flex-wrap gap-2`.
- Sections empilées : `flex flex-col gap-6`.
- Conteneur de formulaire : `max-w-2xl mx-auto`.

---

## 9. Installation / reproduction — pas à pas

1. **Projet Next.js 15 + Tailwind v4** (ou tout projet supportant Tailwind v4).
2. `postcss.config.mjs` :
   ```js
   const config = { plugins: { "@tailwindcss/postcss": {} } };
   export default config;
   ```
3. Créer **`globals.css`** avec le contenu du §4 et l'importer une seule fois
   (dans `layout.tsx` ou l'entrée de l'app).
4. Charger les polices Google (lien du §7.1) dans le `<head>`.
5. Mettre en place le **layout** du §7 (header sticky + main `max-w-5xl` + FAB).
6. Construire les écrans avec les classes `fl-*` + utilitaires Tailwind.
7. Régler `themeColor` et le `viewport` (§7.1) pour un rendu mobile propre.

**Checklist de conformité au thème**
- [ ] Fond `#0e0f11`, cartes `#1c1f25`, bordures `#2a2d35`.
- [ ] Accent doré `#e8c547` sur titres, CTA et état actif.
- [ ] Titres en DM Serif Display ; tout le reste en DM Mono.
- [ ] Corps à `0.85rem`, labels en capitales `0.63rem` espacées.
- [ ] Boutons arrondis 8px, cartes 12px, FAB 20px.
- [ ] FAB violet en bas à droite.
- [ ] Navigation en pilules, onglet actif doré sur fond doré léger.
- [ ] `color-scheme: dark`, aucune variante claire.

---

## 10. Palette rapide (récap copiable)

```
Fond          #0e0f11
Surface       #16181c
Carte         #1c1f25
Bordure       #2a2d35
Accent doré   #e8c547   (hover #f0d25a)
Vert menthe   #4fc3a1
Orange        #e87c47
Violet        #a78bfa
Rouge         #e85c47
Texte         #f0ede6
Atténué       #6b6f7a

Serif : DM Serif Display
Mono  : DM Mono (300 / 400 / 500)
Rayons: 8 / 12 / 20 px
```

---

*Fin du cahier des charges — thème RecipeLog.*
