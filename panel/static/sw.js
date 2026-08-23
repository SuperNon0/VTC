/* Service worker VTC — PWA + Web Push (cahier §6.5 / §7).
 *
 * Volontairement minimal : pas de cache offline agressif (les données de
 * course doivent rester fraîches). Rôle principal : recevoir les notifications
 * push et router le clic vers le calendrier.
 */

self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

// Réception d'une notification push (nouvelle course assignée).
self.addEventListener('push', function (event) {
  var data = { title: 'Nouvelle course', body: '', url: '/' };
  if (event.data) {
    try { data = Object.assign(data, event.data.json()); }
    catch (e) { data.body = event.data.text(); }
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      data: { url: data.url || '/' },
      tag: 'course',
      renotify: true,
    })
  );
});

// Clic sur la notification : ouvre (ou focus) l'app sur le calendrier.
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
