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
        return k === CACHE ? null : caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

// Stale-while-revalidate : sert la version en cache immédiatement (rapide) et
// rafraîchit en arrière-plan. Uniquement pour les ressources statiques.
self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;          // POST/PUT… → réseau direct
  var url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (!estStatiqueMemeOrigine(url) && !estPoliceGoogle(url)) return;  // pages/api → réseau

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
