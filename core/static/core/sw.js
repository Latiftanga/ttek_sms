// Service Worker for School Management System
// Provides offline support and caching for better performance on slow networks
//
// IMPORTANT: Increment CACHE_VERSION when deploying updates to force cache refresh
// Format: 'v{major}.{minor}' - bump minor for small changes, major for breaking changes

const CACHE_VERSION = 'v1.4';
const CACHE_NAME = `sms-cache-${CACHE_VERSION}`;
const OFFLINE_URL = '/offline/';

// Assets to cache immediately on install (critical for slow connections)
const PRECACHE_ASSETS = [
    OFFLINE_URL,
    '/static/css/dist/styles.css',
    '/static/fontawesome/css/all.min.css',
    '/static/fontawesome/webfonts/fa-solid-900.woff2',
    '/static/fontawesome/webfonts/fa-regular-400.woff2',
];

// Install event - cache critical assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[SW] Precaching assets');
                return cache.addAll(PRECACHE_ASSETS);
            })
            .then(() => self.skipWaiting())
            .catch((err) => console.error('[SW] Precache failed:', err))
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name.startsWith('sms-cache-') && name !== CACHE_NAME)
                        .map((name) => {
                            console.log('[SW] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => self.clients.claim())
    );
});

// Fetch event - network first, fallback to cache, then offline page
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Skip non-GET requests (let POST/PUT/DELETE go through normally)
    if (request.method !== 'GET') {
        return;
    }

    // Skip cross-origin requests (CDN assets will be handled by browser)
    if (url.origin !== location.origin) {
        return;
    }

    // Skip admin, API, and media URLs
    if (url.pathname.startsWith('/admin/') ||
        url.pathname.startsWith('/api/') ||
        url.pathname.startsWith('/media/')) {
        return;
    }

    // For navigation requests (HTML pages)
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    // Cache successful responses for offline access
                    if (response.ok) {
                        const responseClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, responseClone);
                        });
                    }
                    return response;
                })
                .catch(() => {
                    // Network failed - try cache, then offline page
                    return caches.match(request)
                        .then((cachedResponse) => {
                            if (cachedResponse) {
                                return cachedResponse;
                            }
                            return caches.match(OFFLINE_URL);
                        });
                })
        );
        return;
    }

    // For static assets - cache first, then network
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request)
                .then((cachedResponse) => {
                    if (cachedResponse) {
                        // Return cached version, but update cache in background
                        event.waitUntil(
                            fetch(request)
                                .then((response) => {
                                    if (response.ok) {
                                        caches.open(CACHE_NAME).then((cache) => {
                                            cache.put(request, response);
                                        });
                                    }
                                })
                                .catch(() => {})
                        );
                        return cachedResponse;
                    }
                    // Not in cache - fetch and cache
                    return fetch(request)
                        .then((response) => {
                            if (response.ok) {
                                const responseClone = response.clone();
                                caches.open(CACHE_NAME).then((cache) => {
                                    cache.put(request, responseClone);
                                });
                            }
                            return response;
                        });
                })
        );
        return;
    }

    // For HTMX partial requests - network first, fallback to cache
    // Always try to get fresh content, only use cache when offline
    if (request.headers.get('HX-Request')) {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    // Cache successful responses for offline fallback
                    if (response.ok) {
                        const responseClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, responseClone);
                        });
                    }
                    return response;
                })
                .catch(() => {
                    // Network failed - try cache, then show offline message
                    return caches.match(request)
                        .then((cachedResponse) => {
                            if (cachedResponse) {
                                return cachedResponse;
                            }
                            return new Response(
                                '<div class="alert alert-warning"><i class="fa-solid fa-wifi-slash mr-2"></i>You\'re offline. This content is unavailable.</div>',
                                { headers: { 'Content-Type': 'text/html' } }
                            );
                        });
                })
        );
        return;
    }
});

// Listen for messages from the main thread
self.addEventListener('message', (event) => {
    if (event.data === 'skipWaiting') {
        self.skipWaiting();
    }

    // Clear cache on demand
    if (event.data === 'clearCache') {
        caches.delete(CACHE_NAME).then(() => {
            console.log('[SW] Cache cleared');
        });
    }
});
