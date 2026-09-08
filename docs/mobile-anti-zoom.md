# Ajout au socle — comportement « app native » sur mobile (anti-zoom)

Objectif : que tous les sites générés depuis le socle se comportent comme
une **vraie app native sur mobile**, sans zoom parasite. Cible principale :
iOS / iPad en mode PWA (ajouté à l'écran d'accueil).

Trois modifications, uniquement CSS/HTML, **zéro impact fonctionnel**.

---

## 1. Désactiver le zoom de la page (pincer / double-tap)

**Pourquoi :** sur mobile on peut zoomer/dézoomer la page par accident, ce qui
casse le rendu « app ».

**Comment :** dans le `<head>` de chaque page, la balise viewport devient :

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
```

*(Fichier concerné : le template de base / chaque page HTML.)*

---

## 2. Empêcher le zoom automatique au focus d'un champ

**Pourquoi :** iOS zoome tout seul dès qu'on touche un champ dont la police fait
**moins de 16px** (typiquement les barres de recherche). Très agaçant.

**Comment :** forcer tous les champs à 16px minimum. Une règle globale suffit :

```css
input, select, textarea { font-size: 16px !important; }
```

*(Fichier concerné : `static/style.css`.)*

---

## 3. Fluidité tactile + pas de redimensionnement de texte auto

**Pourquoi :** enlève le délai de ~300 ms au tap, le double-tap-zoom résiduel,
et le redimensionnement de police iOS en mode paysage.

**Comment :** sur le `body` :

```css
body { touch-action: manipulation; -webkit-text-size-adjust: 100%; }
```

*(Fichier concerné : `static/style.css`.)*

---

## À savoir

- Si le site a une **carte interactive** (type Leaflet), son propre zoom reste
  indépendant — ces réglages ne le touchent pas.
- Pour que ça prenne effet côté **iOS**, il faut relancer complètement l'app
  (ou re-ajouter l'icône à l'écran d'accueil : iOS met en cache très
  agressivement les PWA).
