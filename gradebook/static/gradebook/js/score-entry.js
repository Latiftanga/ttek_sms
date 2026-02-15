/**
 * Shared score entry module for table and student views.
 * Uses native HTMX for saving — inputs carry hx-post/hx-trigger/hx-swap="none".
 * Base.html provides: CSRF header, showToast event handler, error/retry toasts.
 *
 * API: ScoreEntry.validateScore(value, max)
 *      ScoreEntry.setupInputs(container)
 *      ScoreEntry.callbacks  — overwritten by each partial's inline script
 */
window.ScoreEntry = (function() {
    'use strict';

    function validateScore(value, max) {
        if (value === '') return { valid: true };
        var num = parseFloat(value);
        if (isNaN(num)) return { valid: false, message: 'Enter a valid number', hint: 'Use digits only (e.g., 85 or 85.5)' };
        if (num < 0) return { valid: false, message: 'Cannot be negative', hint: 'Scores must be 0 or higher' };
        if (num > max) return { valid: false, message: 'Maximum is ' + max, hint: 'Enter a value between 0 and ' + max };
        var decimalPart = value.split('.')[1];
        if (decimalPart && decimalPart.length > 2) {
            return { valid: false, message: 'Max 2 decimal places', hint: 'Use at most 2 decimal places (e.g., 85.75)' };
        }
        return { valid: true };
    }

    // View-specific callbacks — each partial overwrites these
    var callbacks = {
        showErrorTooltip: function() {},
        hideErrorTooltip: function() {},
        markInputError: function() {},
        clearInputError: function() {}
    };

    function markInputError(input, message, hint) {
        input.classList.add('input-error', 'has-error');
        input.dataset.errorMessage = message;
        input.dataset.errorHint = hint || '';
        callbacks.markInputError(input, message, hint);
    }

    function clearInputError(input) {
        input.classList.remove('input-error', 'has-error');
        delete input.dataset.errorMessage;
        delete input.dataset.errorHint;
        callbacks.clearInputError(input);
    }

    // --- Global handlers (attached once) ---
    var SCORE_SELECTOR = '.score-input, .score-input-mobile';

    if (!window._scoreEntryInitialized) {
        window._scoreEntryInitialized = true;

        // Pre-request: validate, skip-if-unchanged, offline gate
        document.body.addEventListener('htmx:beforeRequest', function(e) {
            var input = e.detail.elt;
            if (!input.matches || !input.matches(SCORE_SELECTOR)) return;

            if (!navigator.onLine) {
                e.preventDefault();
                markInputError(input, 'Offline', 'Score will not save until you reconnect');
                if (typeof NetworkManager !== 'undefined') {
                    NetworkManager.showToast('error', '', 'Cannot save while offline');
                }
                return;
            }

            if (input.value.trim() === (input.dataset.originalValue || '')) {
                e.preventDefault();
                return;
            }

            var max = parseFloat(input.dataset.max);
            var validation = validateScore(input.value.trim(), max);
            if (!validation.valid) {
                e.preventDefault();
                markInputError(input, validation.message, validation.hint);
                callbacks.showErrorTooltip(input, validation.message, validation.hint);
                return;
            }

            clearInputError(input);
            input.classList.remove('input-success');
        });

        // Post-request: success flash or error handling
        document.body.addEventListener('htmx:afterRequest', function(e) {
            var input = e.detail.elt;
            if (!input.matches || !input.matches(SCORE_SELECTOR)) return;

            var xhr = e.detail.xhr;
            if (e.detail.successful && xhr) {
                var triggerHeader = xhr.getResponseHeader('HX-Trigger');
                var triggerData = null;
                if (triggerHeader) {
                    try { triggerData = JSON.parse(triggerHeader); } catch(ex) {}
                }

                if (triggerData && triggerData.revertScore) {
                    input.value = triggerData.revertScore.value;
                    input.dataset.originalValue = triggerData.revertScore.value;
                }

                if (triggerData && triggerData.scoreError) {
                    var err = triggerData.scoreError;
                    markInputError(input, err.message, err.hint);
                    callbacks.showErrorTooltip(input, err.message, err.hint);
                    // Re-show toast — base.html afterRequest may have hidden it
                    if (triggerData.showToast && typeof NetworkManager !== 'undefined') {
                        NetworkManager.showToast(
                            triggerData.showToast.type || 'error', '',
                            triggerData.showToast.message
                        );
                    }
                } else {
                    input.dataset.originalValue = input.value.trim();
                    input.classList.add('input-success');
                    setTimeout(function() { input.classList.remove('input-success'); }, 600);
                    clearInputError(input);
                }
            } else if (!e.detail.successful) {
                // Network/server error — base.html shows retry toast
                input.classList.add('input-error');
                setTimeout(function() { input.classList.remove('input-error'); }, 2000);
            }
        });

        // Offline banner toggle
        function updateOfflineBanners(offline) {
            ['offline-banner', 'offline-banner-mobile'].forEach(function(id) {
                var el = document.getElementById(id);
                if (el) el.classList.toggle('hidden', !offline);
            });
        }

        window.addEventListener('online', function() { updateOfflineBanners(false); });
        window.addEventListener('offline', function() { updateOfflineBanners(true); });
        updateOfflineBanners(!navigator.onLine);
    }

    // --- Per-container setup (called by each partial) ---
    function setupInputs(container) {
        if (!container) return;

        var inputSelector = '.score-input:not([disabled]), .score-input-mobile:not([disabled])';
        var typingDebounceTimer = null;

        // Store original values
        container.querySelectorAll(inputSelector).forEach(function(input) {
            input.dataset.originalValue = input.value;
        });

        // Real-time validation while typing
        container.addEventListener('input', function(e) {
            if (!e.target.matches(inputSelector)) return;
            var input = e.target;
            var value = input.value.trim();
            var max = parseFloat(input.dataset.max);
            var validation = validateScore(value, max);

            if (typingDebounceTimer) clearTimeout(typingDebounceTimer);

            if (!validation.valid && value !== '') {
                input.classList.add('input-error');
                typingDebounceTimer = setTimeout(function() {
                    callbacks.showErrorTooltip(input, validation.message, validation.hint);
                }, 150);
            } else {
                input.classList.remove('input-error');
                callbacks.hideErrorTooltip();
                if (input.classList.contains('has-error') && validation.valid) {
                    clearInputError(input);
                }
            }
        });

        // Show tooltip on focus if has error
        container.addEventListener('focusin', function(e) {
            if (!e.target.matches(inputSelector)) return;
            var input = e.target;
            if (input.classList.contains('has-error') && input.dataset.errorMessage) {
                callbacks.showErrorTooltip(input, input.dataset.errorMessage, input.dataset.errorHint);
            }
        });

        // Hide tooltip on blur
        container.addEventListener('focusout', function(e) {
            if (!e.target.matches(inputSelector)) return;
            callbacks.hideErrorTooltip();
        });

        // Keyboard: Enter saves + moves next, Escape hides tooltip
        container.addEventListener('keydown', function(e) {
            if (!e.target.matches(inputSelector)) return;
            var input = e.target;

            if (e.key === 'Enter') {
                e.preventDefault();
                input.dispatchEvent(new Event('change', { bubbles: true }));
                var inputs = container.querySelectorAll(inputSelector);
                var arr = Array.prototype.slice.call(inputs);
                var idx = arr.indexOf(input);
                var nextInput = arr[idx + 1];
                if (nextInput) {
                    setTimeout(function() {
                        nextInput.focus();
                        nextInput.select();
                    }, 100);
                }
            }

            if (e.key === 'Escape') {
                callbacks.hideErrorTooltip();
            }
        });
    }

    return {
        validateScore: validateScore,
        setupInputs: setupInputs,
        callbacks: callbacks
    };
})();
