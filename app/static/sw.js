/* Service worker VTC — PWA + Web Push (cahier §6.5 / §7).
 *
 * Deux rôles :
 *   1. Notifications push (nouvelle course assignée) + clic → calendrier.
 *   2. Cache des RESSOURCES STATIQUES uniquement (styles, icônes, polices) pour
 *      un lancement instantané en « version application », même sur réseau lent.
 *
 * Important : les PAGES (HTML) et les appels /api/* ne sont JAMAIS mis en cache
 * → les données de course restent toujours fraîches (récupérées au réseau).
 */

var CACHE = 'vtc-static-v1';                 // ← changer le suffixe purge l'ancien cache
var PAGES = 'vtc-pages-v1';                  // dernières pages vues (mode hors ligne)
var KEEP = [CACHE, PAGES];
var STATIC_RE = /\.(css|woff2?|ttf|otf|png|svg|jpg|jpeg|webp|ico)$/i;

function estStatiqueMemeOrigine(url) {
  return url.origin === self.location.origin
    && url.pathname !== '/sw.js'             // ne jamais mettre le SW lui-même en cache
    && STATIC_RE.test(url.pathname);
}
function estPoliceGoogle(url) {
  return url.hostname === 'fonts.googleapis.com'
    || url.hostname === 'fonts.gstatic.com';
}

self.addEventListener('install', function () {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  // Purge les anciens caches (versions précédentes) puis prend la main.
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        return KEEP.indexOf(k) === -1 ? caches.delete(k) : null;
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

// Stale-while-revalidate : sert la version en cache immédiatement (rapide) et
// rafraîchit en arrière-plan. Uniquement pour les ressources statiques.
var OFFLINE_HTML =
  '<!doctype html><html lang="fr"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>Hors ligne</title><style>' +
  'body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;' +
  'justify-content:center;gap:14px;background:#0e0f11;color:#f0ede6;' +
  'font-family:ui-monospace,Menlo,monospace;text-align:center;padding:24px}' +
  'h1{font-size:1.2rem;margin:0;color:#e8c547}p{color:#6b6f7a;font-size:.9rem;line-height:1.5;margin:0;max-width:300px}' +
  'button{margin-top:8px;background:#e8c547;color:#0e0f11;border:0;border-radius:10px;' +
  'padding:.7rem 1.4rem;font:inherit;font-weight:600}</style></head><body>' +
  '<h1>Pas de connexion</h1><p>Tu es hors ligne et cette page n\'a pas encore été ' +
  'consultée. Reconnecte-toi pour voir tes courses à jour.</p>' +
  '<button onclick="location.reload()">Réessayer</button></body></html>';

function reponseOffline() {
  return new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;          // POST/PUT… → réseau direct
  var url;
  try { url = new URL(req.url); } catch (e) { return; }

  // ── Navigations (pages HTML) : réseau d'abord, cache en secours (hors ligne) ─
  // En ligne : toujours la version fraîche (et on en garde une copie). Hors ligne :
  // on réaffiche la dernière page vue, sinon une page « hors ligne ».
  if (req.mode === 'navigate' && url.origin === self.location.origin) {
    event.respondWith(
      fetch(req).then(function (resp) {
        if (resp && resp.ok) {
          var copie = resp.clone();
          caches.open(PAGES).then(function (c) { c.put(req, copie); });
        }
        return resp;
      }).catch(function () {
        return caches.open(PAGES).then(function (c) {
          return c.match(req).then(function (hit) { return hit || c.match('/'); });
        }).then(function (r) { return r || reponseOffline(); });
      })
    );
    return;
  }

  if (!estStatiqueMemeOrigine(url) && !estPoliceGoogle(url)) return;  // /api → réseau

  event.respondWith(
    caches.open(CACHE).then(function (cache) {
      return cache.match(req).then(function (hit) {
        var reseau = fetch(req).then(function (resp) {
          // 200 (même origine) ou réponse opaque (polices cross-origin) → on garde.
          if (resp && (resp.ok || resp.type === 'opaque')) {
            cache.put(req, resp.clone());
          }
          return resp;
        }).catch(function () { return hit; });  // hors ligne → dernière version connue
        return hit || reseau;                    // cache d'abord, sinon réseau
      });
    })
  );
});

// ── Réception d'une notification push (nouvelle course assignée) ──────────────
self.addEventListener('push', function (event) {
  var data = { title: 'Nouvelle course', body: '', url: '/' };
  if (event.data) {
    try { data = Object.assign(data, event.data.json()); }
    catch (e) { data.body = event.data.text(); }
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/app/icon-192.png',
      badge: '/app/icon-192.png',
      data: { url: data.url || '/' },
      tag: 'course',
      renotify: true,
    })
  );
});

// ── Clic sur la notification : ouvre (ou focus) l'app sur le calendrier ───────
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var target = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if ('focus' in list[i]) { list[i].navigate(target); return list[i].focus(); }
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
    })
  );
});
