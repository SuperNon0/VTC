-- ─────────────────────────── Modèle métier taxi/VTC ───────────────────────────
-- Exécuté en plus du schéma de la base (base/panel/db.py) au démarrage.
-- Toutes les tables sont en CREATE IF NOT EXISTS : sur une base existante, les
-- données sont conservées ; sur une base neuve, tout est créé.

-- Nom d'affichage par compte (la base ne stocke que l'e-mail). Convention
-- `compte_id` → la base sait réattribuer/fusionner ces lignes (cf. set_email).
CREATE TABLE IF NOT EXISTS vtc_profils (
    compte_id INTEGER PRIMARY KEY,
    nom       TEXT,
    FOREIGN KEY (compte_id) REFERENCES comptes(id) ON DELETE CASCADE
);

-- Clients habitués (cahier §6.4).
CREATE TABLE IF NOT EXISTS clients (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nom       TEXT NOT NULL,
    telephone TEXT,
    adresses  TEXT,             -- JSON : liste d'adresses fréquentes
    notes     TEXT,
    cree      INTEGER
);

-- Villes desservies (liste gérable). Rattachées aux lieux (ville_id) et
-- proposées en suggestion dans les formulaires (course + lieu).
CREATE TABLE IF NOT EXISTS villes (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    nom   TEXT NOT NULL,
    ordre INTEGER NOT NULL DEFAULT 0
);

-- Lieux fréquents présélectionnables dans le formulaire (cahier §6.2).
-- `ville_id` rattache le lieu à une ville (colonne ajoutée après coup sur les
-- bases existantes par app.courses.ensure_schema()).
CREATE TABLE IF NOT EXISTS lieux (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nom      TEXT NOT NULL,
    adresse  TEXT,
    ville_id INTEGER,
    ordre    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (ville_id) REFERENCES villes(id) ON DELETE SET NULL
);

-- Grilles tarifaires (cahier §6.3) : un tarif relie un départ à une arrivée.
-- Chaque extrémité est SOIT un lieu fréquent (lieu_*_id), SOIT une ville
-- (ville_*_id) — l'une des deux extrémités peut rester vide (joker) →
-- auto-sélection à la création d'une course.
CREATE TABLE IF NOT EXISTS tarifs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    libelle         TEXT NOT NULL,
    prix            REAL NOT NULL,
    lieu_depart_id  INTEGER,
    lieu_arrivee_id INTEGER,
    ville_depart_id  INTEGER,
    ville_arrivee_id INTEGER,
    ordre           INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (lieu_depart_id)  REFERENCES lieux(id) ON DELETE SET NULL,
    FOREIGN KEY (lieu_arrivee_id) REFERENCES lieux(id) ON DELETE SET NULL,
    FOREIGN KEY (ville_depart_id)  REFERENCES villes(id) ON DELETE SET NULL,
    FOREIGN KEY (ville_arrivee_id) REFERENCES villes(id) ON DELETE SET NULL
);

-- Courses (cahier §5). Créateur ≠ conducteur assigné (tous deux → comptes.id).
CREATE TABLE IF NOT EXISTS courses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_nom     TEXT,
    client_tel     TEXT,
    depart         TEXT,
    arrivee        TEXT,
    quand          INTEGER,
    prix           REAL,
    prix_source    TEXT,
    tarif_id       INTEGER,
    distance_km    REAL,
    duree_min      INTEGER,
    statut         TEXT NOT NULL DEFAULT 'a_faire',
    createur_id    INTEGER NOT NULL,
    conducteur_id  INTEGER NOT NULL,
    client_id      INTEGER,
    notes          TEXT,
    cree           INTEGER,
    maj            INTEGER,
    FOREIGN KEY (createur_id)   REFERENCES comptes(id),
    FOREIGN KEY (conducteur_id) REFERENCES comptes(id),
    FOREIGN KEY (tarif_id)      REFERENCES tarifs(id) ON DELETE SET NULL,
    FOREIGN KEY (client_id)     REFERENCES clients(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_courses_conducteur ON courses(conducteur_id, quand);
CREATE INDEX IF NOT EXISTS idx_courses_createur   ON courses(createur_id, quand);

-- Abonnements Web Push (cahier §6.5 / §7). Un appareil = une souscription.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    compte_id INTEGER NOT NULL,
    endpoint  TEXT NOT NULL UNIQUE,
    p256dh    TEXT NOT NULL,
    auth      TEXT NOT NULL,
    ua        TEXT,
    cree      INTEGER,
    FOREIGN KEY (compte_id) REFERENCES comptes(id) ON DELETE CASCADE
);
