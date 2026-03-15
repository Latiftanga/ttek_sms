/**
 * Offline Score Queue — IndexedDB-backed queue for saving scores while offline.
 *
 * When offline, scores are stored locally in IndexedDB. When back online,
 * they are synced to the server in order. Duplicate entries (same student +
 * assignment) are deduplicated, keeping only the latest value.
 *
 * API:
 *   OfflineScores.enqueue(studentId, assignmentId, points, csrfToken)
 *   OfflineScores.pendingCount()  → Promise<number>
 *   OfflineScores.sync()          → Promise  (called automatically on reconnect)
 *   OfflineScores.onCountChange   — callback(count) fired when queue changes
 */
window.OfflineScores = (function() {
    'use strict';

    var DB_NAME = 'sms_offline_scores';
    var DB_VERSION = 1;
    var STORE_NAME = 'queue';
    var SAVE_URL = '/gradebook/scores/save/';
    var db = null;
    var syncing = false;
    var onCountChange = null;

    // --- IndexedDB helpers ---

    function openDB() {
        if (db) return Promise.resolve(db);
        return new Promise(function(resolve, reject) {
            var request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = function(e) {
                var store = e.target.result.createObjectStore(STORE_NAME, { keyPath: 'key' });
                store.createIndex('timestamp', 'timestamp', { unique: false });
            };
            request.onsuccess = function(e) {
                db = e.target.result;
                resolve(db);
            };
            request.onerror = function(e) {
                console.error('[OfflineScores] DB open error:', e.target.error);
                reject(e.target.error);
            };
        });
    }

    function getStore(mode) {
        return openDB().then(function(db) {
            var tx = db.transaction(STORE_NAME, mode);
            return tx.objectStore(STORE_NAME);
        });
    }

    // --- Public API ---

    function enqueue(studentId, assignmentId, points, csrfToken) {
        // Deduplicate: use student+assignment as key so latest value wins
        var key = studentId + ':' + assignmentId;
        var record = {
            key: key,
            studentId: String(studentId),
            assignmentId: String(assignmentId),
            points: points,
            csrfToken: csrfToken,
            timestamp: Date.now()
        };
        return openDB().then(function(db) {
            return new Promise(function(resolve, reject) {
                var tx = db.transaction(STORE_NAME, 'readwrite');
                var store = tx.objectStore(STORE_NAME);
                store.put(record);
                tx.oncomplete = function() {
                    notifyCount();
                    resolve();
                };
                tx.onerror = function(e) { reject(e.target.error); };
            });
        });
    }

    function pendingCount() {
        return openDB().then(function(db) {
            return new Promise(function(resolve, reject) {
                var tx = db.transaction(STORE_NAME, 'readonly');
                var store = tx.objectStore(STORE_NAME);
                var countReq = store.count();
                countReq.onsuccess = function() { resolve(countReq.result); };
                countReq.onerror = function(e) { reject(e.target.error); };
            });
        }).catch(function() { return 0; });
    }

    function getAll() {
        return openDB().then(function(db) {
            return new Promise(function(resolve, reject) {
                var tx = db.transaction(STORE_NAME, 'readonly');
                var store = tx.objectStore(STORE_NAME);
                var index = store.index('timestamp');
                var req = index.getAll();
                req.onsuccess = function() { resolve(req.result); };
                req.onerror = function(e) { reject(e.target.error); };
            });
        });
    }

    function remove(key) {
        return openDB().then(function(db) {
            return new Promise(function(resolve, reject) {
                var tx = db.transaction(STORE_NAME, 'readwrite');
                tx.objectStore(STORE_NAME).delete(key);
                tx.oncomplete = function() { resolve(); };
                tx.onerror = function(e) { reject(e.target.error); };
            });
        });
    }

    function notifyCount() {
        pendingCount().then(function(count) {
            if (typeof onCountChange === 'function') onCountChange(count);
            updateBanners(count);
        });
    }

    // --- Sync logic ---

    function sync() {
        if (syncing || !navigator.onLine) return Promise.resolve();
        syncing = true;

        return getAll().then(function(records) {
            if (!records.length) {
                syncing = false;
                return;
            }
            showSyncIndicator(records.length);
            return syncNext(records, 0);
        }).catch(function(err) {
            console.error('[OfflineScores] Sync error:', err);
            syncing = false;
        });
    }

    function syncNext(records, idx) {
        if (idx >= records.length || !navigator.onLine) {
            syncing = false;
            hideSyncIndicator();
            notifyCount();
            return Promise.resolve();
        }

        var rec = records[idx];
        updateSyncProgress(idx + 1, records.length);

        var formData = new FormData();
        formData.append('student_id', rec.studentId);
        formData.append('assignment_id', rec.assignmentId);
        formData.append('points', rec.points);

        return fetch(SAVE_URL, {
            method: 'POST',
            headers: {
                'X-CSRFToken': rec.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData,
            credentials: 'same-origin'
        }).then(function(response) {
            if (response.ok || response.status === 400 || response.status === 403) {
                // Remove from queue on success OR on validation/auth errors
                // (retrying won't fix auth/validation issues)
                return remove(rec.key).then(function() {
                    return syncNext(records, idx + 1);
                });
            }
            // Server error (500) — stop syncing, retry later
            throw new Error('Server error ' + response.status);
        }).catch(function(err) {
            console.warn('[OfflineScores] Sync failed at item', idx, err);
            syncing = false;
            hideSyncIndicator();
            notifyCount();
        });
    }

    // --- UI helpers ---

    function updateBanners(count) {
        ['offline-banner', 'offline-banner-mobile'].forEach(function(id) {
            var el = document.getElementById(id);
            if (!el) return;

            var badge = el.querySelector('.offline-queue-badge');
            if (count > 0 && !navigator.onLine) {
                el.classList.remove('hidden');
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'offline-queue-badge badge badge-sm ml-1';
                    el.querySelector('span').appendChild(badge);
                }
                badge.textContent = count + ' queued';
            } else if (count > 0 && navigator.onLine) {
                // Online with pending items — sync will handle
                if (badge) badge.remove();
            } else {
                if (badge) badge.remove();
            }
        });
    }

    function showSyncIndicator(total) {
        var existing = document.getElementById('offline-sync-indicator');
        if (existing) existing.remove();

        var div = document.createElement('div');
        div.id = 'offline-sync-indicator';
        div.className = 'fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-72 z-50 alert alert-info shadow-lg py-2 px-3';
        div.innerHTML =
            '<i class="fa-solid fa-cloud-arrow-up animate-pulse"></i>' +
            '<div class="flex-1">' +
                '<div class="font-semibold text-sm">Syncing offline scores</div>' +
                '<div class="text-xs mt-0.5"><span id="sync-progress">0</span> / ' + total + '</div>' +
                '<progress id="sync-progress-bar" class="progress progress-primary w-full mt-1" value="0" max="' + total + '"></progress>' +
            '</div>';
        document.body.appendChild(div);
    }

    function updateSyncProgress(current, total) {
        var el = document.getElementById('sync-progress');
        var bar = document.getElementById('sync-progress-bar');
        if (el) el.textContent = current;
        if (bar) bar.value = current;
    }

    function hideSyncIndicator() {
        var el = document.getElementById('offline-sync-indicator');
        if (el) {
            el.classList.add('alert-success');
            el.classList.remove('alert-info');
            el.querySelector('i').className = 'fa-solid fa-check';
            el.querySelector('.font-semibold').textContent = 'All scores synced!';
            setTimeout(function() {
                if (el.parentNode) el.remove();
            }, 2500);
        }
    }

    // --- Auto-sync on reconnect ---

    window.addEventListener('online', function() {
        // Small delay to let the network stabilize
        setTimeout(function() { sync(); }, 1000);
    });

    // Sync on page load if there are pending items
    if (typeof document !== 'undefined') {
        document.addEventListener('DOMContentLoaded', function() {
            if (navigator.onLine) {
                pendingCount().then(function(count) {
                    if (count > 0) sync();
                });
            } else {
                notifyCount();
            }
        });
    }

    return {
        enqueue: enqueue,
        pendingCount: pendingCount,
        sync: sync,
        get onCountChange() { return onCountChange; },
        set onCountChange(fn) { onCountChange = fn; }
    };
})();
