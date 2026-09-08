-- Tables métier du projet (exemple). Exécuté en plus du schéma de la base.
-- Convention : une colonne `compte_id` → la base sait réattribuer/fusionner
-- ces lignes (voir set_email) et tu peux cloisonner par utilisateur.

CREATE TABLE IF NOT EXISTS exemple_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    compte_id  INTEGER NOT NULL,   -- propriétaire (données cloisonnées)
    titre      TEXT NOT NULL,
    cree       INTEGER
);
