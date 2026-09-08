#!/usr/bin/env python3
"""Batterie de tests du site (modèle en couches).

Couvre : démarrage, gateway/login LAN, sécurité des API (401 + no-store),
permissions, cycle de vie des comptes (pending→actif/refused/bloqué/supprimé),
dernier super-admin indestructible, impersonation, site « perso » (auto-actif),
réglages base vs application, mise à jour (garde impersonation), surcouche
(templates/schema/register + point d'extension /reglages), et utilitaires.

Aucune dépendance externe : lance-le avec le Python du venv.

    .venv/bin/python tests/test_site.py

Ne touche PAS au dépôt : DB temporaire, dossier app/ créé puis supprimé.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
APP_EXAMPLE = os.path.join(ROOT, "app.example")
DB = os.path.join(tempfile.gettempdir(), "sitebase_tests.db")

_PASS = 0
_FAIL = 0


def check(cond, label):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  \033[32mok\033[0m   {label}")
    else:
        _FAIL += 1
        print(f"  \033[31mFAIL\033[0m {label}")


def section(title):
    print(f"\n\033[1m{title}\033[0m")


# --------------------------------------------------------------------------- #
#  Fabrique d'app : env → modules neufs → create_app (DB temp)
# --------------------------------------------------------------------------- #
BASE_ENV = {
    "SECRET_KEY": "t" * 40,
    "DATABASE_PATH": DB,
    "CF_VERIFY_JWT": "false",       # e-mail Cloudflare simulé via en-tête
    "ALLOW_LOCAL_LOGIN": "true",
    "SUPERADMIN_PASSWORD": "motdepasse-initial",
    "SUPERADMIN_EMAIL": "admin@site.fr",
    "BOTPANEL_URL": "",             # notify() court-circuité → aucun réseau
    "BRAND_PREFIX": "Site", "BRAND_SUFFIX": "Base", "BRAND_BADGE": "test",
}


def _reset_modules():
    for m in list(sys.modules):
        if m == "panel" or m.startswith("panel.") or m == "app" or m.startswith("app."):
            del sys.modules[m]
    sys.path[:] = [p for p in sys.path if p not in (ROOT, os.path.join(ROOT, "base"))]
    sys.path.insert(0, os.path.join(ROOT, "base"))
    sys.path.insert(0, ROOT)


def make_app(overrides=None, with_overlay=False):
    if os.path.exists(DB):
        os.remove(DB)
    if with_overlay and not os.path.isdir(APP_DIR):
        shutil.copytree(APP_EXAMPLE, APP_DIR)
    if not with_overlay and os.path.isdir(APP_DIR):
        shutil.rmtree(APP_DIR)
    env = dict(BASE_ENV)
    env.update(overrides or {})
    for k in ("CAP_ACCOUNT_MANAGEMENT", "CAP_PROFILES", "CAP_ADMIN_PASSWORD",
              "CAP_SITE_UPDATE"):
        os.environ.pop(k, None)
    os.environ.update(env)
    _reset_modules()
    import panel
    importlib.reload(panel)
    app = panel.create_app()
    app.config["TESTING"] = True
    return app


def as_admin(client, compte_id=1):
    with client.session_transaction() as s:
        s["compte_id"] = compte_id
        s["role"] = "super_admin"


def cf(email):
    """En-têtes simulant un utilisateur authentifié par Cloudflare Access."""
    return {"Cf-Access-Authenticated-User-Email": email}


HUB = {"CAP_ACCOUNT_MANAGEMENT": "super_admin", "CAP_PROFILES": "super_admin",
       "CAP_ADMIN_PASSWORD": "super_admin", "CAP_SITE_UPDATE": "super_admin"}


# --------------------------------------------------------------------------- #
def test_boot_and_gateway():
    section("1. Démarrage & gateway (accès LAN)")
    app = make_app(HUB)
    c = app.test_client()
    r = c.get("/")
    check(r.status_code in (301, 302), "GET / non connecté → redirection")
    r = c.get("/gateway")
    check(r.status_code == 200 and "login" in r.get_data(as_text=True).lower(),
          "GET /gateway sans Cloudflare → page login (200)")
    r = c.get("/login")
    check(r.status_code == 302, "GET /login → 302 (pas de 405)")


def test_login_local():
    section("2. Login local par mot de passe")
    app = make_app(HUB)
    c = app.test_client()
    r = c.post("/login", data={"password": "mauvais"}, follow_redirects=False)
    check(r.status_code == 302, "mauvais mot de passe → redirection (refus)")
    with c.session_transaction() as s:
        check("compte_id" not in s, "mauvais mot de passe → pas de session")
    r = c.post("/login", data={"password": "motdepasse-initial"}, follow_redirects=False)
    check(r.status_code == 302, "bon mot de passe → redirection")
    with c.session_transaction() as s:
        check(s.get("compte_id") == 1, "bon mot de passe → session ouverte")
    r = c.get("/logout", follow_redirects=False)
    with c.session_transaction() as s:
        check("compte_id" not in s, "logout → session vidée")


def test_api_security():
    section("3. Sécurité des API (/api/* : 401 + no-store)")
    app = make_app(HUB)
    c = app.test_client()
    r = c.get("/api/system/info")
    check(r.status_code == 401, "GET /api/system/info non connecté → 401")
    check(r.headers.get("Cache-Control") == "no-store", "réponse /api/* → Cache-Control: no-store")
    r = c.post("/api/comptes/999/valider")
    check(r.status_code in (401, 403), "POST /api/comptes/.../valider non connecté → 401/403")


def test_permissions_pages():
    section("4. Permissions (pages admin)")
    app = make_app(HUB)
    c = app.test_client()
    r = c.get("/parametres")
    check(r.status_code == 302, "/parametres non connecté → redirection login")
    as_admin(c)
    r = c.get("/parametres")
    check(r.status_code == 200 and "Paramètres" in r.get_data(as_text=True),
          "/parametres en super-admin → 200")
    r = c.get("/api/system/info")
    check(r.status_code == 200 and r.is_json, "/api/system/info en super-admin → 200 JSON")
    d = r.get_json()
    check("base_version" in d, "info expose base_version (couche base)")


def test_comptes_lifecycle():
    section("5. Cycle de vie des comptes (hub)")
    app = make_app(HUB)
    c = app.test_client()

    # Une demande d'accès (utilisateur Cloudflare inconnu) → pending
    c.post("/request-access", headers=cf("membre@site.fr"))
    from panel.db import get_db
    with app.app_context():
        row = get_db().execute("SELECT id, etat FROM comptes WHERE email = ?",
                               ("membre@site.fr",)).fetchone()
    check(row is not None and row["etat"] == "pending", "request-access → compte pending créé")
    cid = row["id"]

    as_admin(c)
    r = c.post(f"/api/comptes/{cid}/valider")
    check(r.status_code == 302, "valider → 302")
    with app.app_context():
        etat = get_db().execute("SELECT etat FROM comptes WHERE id = ?", (cid,)).fetchone()["etat"]
    check(etat == "actif", "valider → état actif")

    r = c.post(f"/api/comptes/{cid}/bloquer")
    with app.app_context():
        etat = get_db().execute("SELECT etat FROM comptes WHERE id = ?", (cid,)).fetchone()["etat"]
    check(etat == "bloque", "bloquer → état bloqué")

    r = c.post(f"/api/comptes/{cid}/debloquer")
    with app.app_context():
        etat = get_db().execute("SELECT etat FROM comptes WHERE id = ?", (cid,)).fetchone()["etat"]
    check(etat == "actif", "debloquer → état actif")

    r = c.post(f"/api/comptes/{cid}/supprimer")
    with app.app_context():
        gone = get_db().execute("SELECT 1 FROM comptes WHERE id = ?", (cid,)).fetchone()
    check(gone is None, "supprimer membre → compte retiré")

    # Dernier super-admin indestructible
    r = c.post("/api/comptes/1/supprimer")
    with app.app_context():
        still = get_db().execute("SELECT 1 FROM comptes WHERE id = 1").fetchone()
    check(still is not None, "supprimer super-admin → refusé (indestructible)")


def test_refuser():
    section("6. Refus d'une demande")
    app = make_app(HUB)
    c = app.test_client()
    c.post("/request-access", headers=cf("refuse@site.fr"))
    from panel.db import get_db
    with app.app_context():
        cid = get_db().execute("SELECT id FROM comptes WHERE email=?", ("refuse@site.fr",)).fetchone()["id"]
    as_admin(c)
    c.post(f"/api/comptes/{cid}/refuser")
    with app.app_context():
        etat = get_db().execute("SELECT etat FROM comptes WHERE id=?", (cid,)).fetchone()["etat"]
    check(etat == "refused", "refuser → état refused")
    # Redemander : refused → pending
    c.post("/request-access", headers=cf("refuse@site.fr"))
    with app.app_context():
        etat = get_db().execute("SELECT etat FROM comptes WHERE id=?", (cid,)).fetchone()["etat"]
    check(etat == "pending", "redemander un accès → refused repasse pending")


def test_impersonation():
    section("7. Impersonation « voir en tant que »")
    app = make_app(HUB)
    c = app.test_client()
    from panel.db import get_db
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO comptes (email, role, etat, cree) VALUES "
                   "('cible@site.fr','membre','actif',0)")
        db.commit()
        cid = db.execute("SELECT id FROM comptes WHERE email='cible@site.fr'").fetchone()["id"]
    as_admin(c)
    r = c.post(f"/api/comptes/{cid}/impersonate")
    check(r.status_code == 302, "impersonate → 302")
    with c.session_transaction() as s:
        check(s.get("compte_id") == cid and s.get("impersonator_id") == 1,
              "impersonate → session bascule + impersonator mémorisé")
    r = c.get("/parametres")
    check("cible@site.fr" in r.get_data(as_text=True), "bandeau d'impersonation visible")
    # Impersonate un super-admin → interdit
    with c.session_transaction() as s:
        s["compte_id"] = 1
        s.pop("impersonator_id", None)
    r = c.post("/api/comptes/1/impersonate")
    with c.session_transaction() as s:
        check("impersonator_id" not in s, "impersonate super-admin → refusé")
    # Stop
    as_admin(c)
    with c.session_transaction() as s:
        s["impersonator_id"] = 1
        s["compte_id"] = cid
    c.post("/api/impersonate/stop")
    with c.session_transaction() as s:
        check(s.get("compte_id") == 1 and "impersonator_id" not in s,
              "stop impersonation → retour au compte réel")


def test_site_perso():
    section("8. Site « perso » (gestion des comptes off → accès auto en actif)")
    app = make_app({"CAP_ACCOUNT_MANAGEMENT": "off", "CAP_PROFILES": "super_admin"})
    c = app.test_client()
    r = c.get("/gateway", headers=cf("nouveau@site.fr"))
    check(r.status_code in (301, 302), "utilisateur Cloudflare inconnu → entre directement (redirection)")
    from panel.db import get_db
    with app.app_context():
        row = get_db().execute("SELECT etat FROM comptes WHERE email=?", ("nouveau@site.fr",)).fetchone()
    check(row is not None and row["etat"] == "actif", "site perso → compte auto-créé en actif")


def test_settings_and_password():
    section("9. Réglages base : mot de passe, clé/valeur, Cloudflare")
    app = make_app(HUB)
    c = app.test_client()
    from panel.settings import set_setting, get_setting
    with app.app_context():
        set_setting("cle_test", "valeur42")
        check(get_setting("cle_test") == "valeur42", "set_setting/get_setting → persistant")
    as_admin(c)
    r = c.post("/parametres/mot-de-passe", data={
        "actuel": "motdepasse-initial", "nouveau": "nouveaumdp123", "confirme": "nouveaumdp123"},
        follow_redirects=False)
    check(r.status_code == 302, "changer mot de passe → 302")
    # Nouveau mot de passe effectif
    c2 = app.test_client()
    r = c2.post("/login", data={"password": "nouveaumdp123"})
    with c2.session_transaction() as s:
        check(s.get("compte_id") == 1, "login avec le nouveau mot de passe → OK")
    # Ancien refusé
    c3 = app.test_client()
    c3.post("/login", data={"password": "motdepasse-initial"})
    with c3.session_transaction() as s:
        check("compte_id" not in s, "ancien mot de passe → refusé")


def test_superadmin_management():
    section("10. Gestion des super-admins (réservé au compte de base)")
    app = make_app(HUB)
    c = app.test_client()
    as_admin(c)  # compte 1 = super-admin AVEC mdp_hash → compte de base
    r = c.post("/parametres/super-admin/ajouter", data={"email": "sa2@site.fr"},
               follow_redirects=False)
    check(r.status_code == 302, "ajouter super-admin (compte de base) → 302")
    from panel.db import get_db
    with app.app_context():
        row = get_db().execute("SELECT role FROM comptes WHERE email=?", ("sa2@site.fr",)).fetchone()
    check(row is not None and row["role"] == "super_admin", "nouveau super-admin créé")


def test_reglages_base_only():
    section("11. Page /reglages sans surcouche")
    app = make_app(HUB)
    c = app.test_client()
    as_admin(c)
    r = c.get("/reglages")
    body = r.get_data(as_text=True)
    check(r.status_code == 200, "/reglages → 200")
    check("Réglages de l'application" in body, "titre de la page réglages présent")
    check("Aucun réglage" in body, "sans surcouche → « Aucun réglage »")


def test_update_guard_impersonation():
    section("12. Mise à jour bloquée pendant l'impersonation")
    app = make_app(HUB)
    c = app.test_client()
    as_admin(c)
    with c.session_transaction() as s:
        s["impersonator_id"] = 1  # en impersonation
    r = c.post("/api/system/update")
    check(r.status_code == 403, "update pendant impersonation → 403")
    r = c.post("/api/system/sync-base")
    check(r.status_code == 403, "sync-base pendant impersonation → 403")


def test_utils():
    section("13. Utilitaires (date FR)")
    from panel.utils import fmt_dt
    check(fmt_dt(0) == "" and fmt_dt(None) == "", "fmt_dt(0/None) → chaîne vide")
    out = fmt_dt(1_700_000_000)  # timestamp réel
    check(isinstance(out, str) and "20" in out and " à " in out,
          "fmt_dt(ts) → date FR avec heure")


def test_overlay():
    section("14. Surcouche projet (app/) : templates, schema, register, /reglages")
    try:
        app = make_app(HUB, with_overlay=True)
        c = app.test_client()
        from panel.db import get_db
        # schema.sql de la surcouche exécuté
        with app.app_context():
            t = get_db().execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='exemple_items'"
            ).fetchone()
        check(t is not None, "app/schema.sql exécuté (table exemple_items)")
        # register() : l'accueil de la surcouche remplace la démo
        as_admin(c)
        r = c.get("/")
        check(r.status_code == 200, "accueil surcouche servi (200)")
        # point d'extension /reglages
        r = c.get("/reglages")
        body = r.get_data(as_text=True)
        check("Exemple de réglage" in body, "/reglages inclut le partial de la surcouche")
        check("Aucun réglage" not in body, "surcouche → plus de « Aucun réglage »")
        r = c.post("/reglages/enregistrer", data={"app_titre": "Ma cinémathèque"},
                   follow_redirects=True)
        check("Ma cinémathèque" in r.get_data(as_text=True), "réglage app enregistré + affiché")
        r = c.get("/")
        check("Ma cinémathèque" in r.get_data(as_text=True), "accueil reflète le réglage app")
    finally:
        shutil.rmtree(APP_DIR, ignore_errors=True)


def main():
    tests = [
        test_boot_and_gateway, test_login_local, test_api_security,
        test_permissions_pages, test_comptes_lifecycle, test_refuser,
        test_impersonation, test_site_perso, test_settings_and_password,
        test_superadmin_management, test_reglages_base_only,
        test_update_guard_impersonation, test_utils, test_overlay,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            global _FAIL
            _FAIL += 1
            import traceback
            print(f"  \033[31mERREUR\033[0m {t.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n\033[1mRésultat : {_PASS} ok, {_FAIL} échec(s)\033[0m")
    if os.path.exists(DB):
        os.remove(DB)
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
