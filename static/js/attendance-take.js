// Shared by academics/templates/academics/partials/modal_attendance_take.html
// and core/templates/core/teacher/partials/take_attendance_content.html - both
// pages save the same session/student/status shape and share this markup
// contract on #attendance-form:
//   - .student-row[data-name][data-adm], each containing input[type=radio]
//     status buttons (values P/L/A/E) and buttons calling markAll(status)
//   - #present-count / #late-count / #absent-count / #excused-count
//   - #student-search (calls filterStudents(value)) and #search-scope-hint
//   - optional #progress-present/-late/-absent/-excused (only the modal has
//     these; updateSummary() no-ops that part when they're absent)
//
// Wrapped in an IIFE: this script is re-fetched every time its owning
// partial is swapped back in (e.g. changing the date), and top-level
// const/function declarations would otherwise collide with the previous
// injection's on a second load.
(function () {
    const form = document.getElementById('attendance-form');
    if (!form) return;

    const totalStudents = document.querySelectorAll('.student-row').length;
    const hasProgressStrip = !!document.getElementById('progress-present');

    function updateSummary() {
        let present = 0, late = 0, absent = 0, excused = 0;
        form.querySelectorAll('input[type="radio"]:checked').forEach(r => {
            if (r.value === 'P') present++;
            else if (r.value === 'L') late++;
            else if (r.value === 'A') absent++;
            else if (r.value === 'E') excused++;
        });
        document.getElementById('present-count').textContent = present;
        document.getElementById('late-count').textContent = late;
        document.getElementById('absent-count').textContent = absent;
        document.getElementById('excused-count').textContent = excused;

        if (hasProgressStrip) {
            const pct = n => totalStudents > 0 ? (n / totalStudents * 100) + '%' : '0%';
            document.getElementById('progress-present').style.width = pct(present);
            document.getElementById('progress-late').style.width = pct(late);
            document.getElementById('progress-absent').style.width = pct(absent);
            document.getElementById('progress-excused').style.width = pct(excused);
        }
    }

    function updateRowBackground(radio) {
        const row = radio.closest('.student-row');
        if (!row) return;
        row.classList.remove('bg-success/10', 'bg-warning/10', 'bg-error/10', 'bg-info/10');
        if (radio.value === 'P') row.classList.add('bg-success/10');
        else if (radio.value === 'L') row.classList.add('bg-warning/10');
        else if (radio.value === 'A') row.classList.add('bg-error/10');
        else if (radio.value === 'E') row.classList.add('bg-info/10');
    }

    // Lives on window, not a per-injection closure variable - this script
    // re-runs every time its partial is swapped back in (e.g. changing the
    // date, per the file header above), and the window-level listeners
    // registered below are only ever attached once (guarded further down).
    // A closure-local `formDirty` would leave that one-time listener stuck
    // reading whichever injection's copy happened to be in scope when it
    // was first registered, instead of the current form's actual state.
    window.attendanceFormDirty = false;

    // Called from inline onclick/oninput attributes, so must stay global.
    window.filterStudents = function (query) {
        const q = query.toLowerCase().trim();
        let visible = 0;
        document.querySelectorAll('.student-row').forEach(row => {
            const name = row.dataset.name || '';
            const adm = row.dataset.adm || '';
            const show = !q || name.includes(q) || adm.includes(q);
            row.style.display = show ? '' : 'none';
            if (show) visible++;
        });
        const hint = document.getElementById('search-scope-hint');
        if (!hint) return;
        if (q) {
            hint.textContent = `Bulk status buttons above apply only to the ${visible} student${visible === 1 ? '' : 's'} shown.`;
            hint.classList.remove('hidden');
        } else {
            hint.classList.add('hidden');
        }
    };

    // Only touches rows currently visible under the search filter - a
    // teacher who searched down to one student to fix a mistake shouldn't
    // have "All Present" silently re-mark the whole class.
    window.markAll = function (status) {
        const rows = Array.from(document.querySelectorAll('.student-row'))
            .filter(row => row.style.display !== 'none');
        if (!rows.length) return;
        rows.forEach(row => {
            const radio = row.querySelector(`input[type="radio"][value="${status}"]`);
            if (!radio) return;
            radio.checked = true;
            updateRowBackground(radio);
        });
        window.attendanceFormDirty = true;
        updateSummary();
        if (navigator.vibrate) navigator.vibrate(50);
    };

    form.querySelectorAll('input[type="radio"]').forEach(r => {
        r.addEventListener('change', function () {
            updateRowBackground(this);
            updateSummary();
            if (navigator.vibrate) navigator.vibrate(20);
        });
    });
    updateSummary();

    form.addEventListener('change', () => { window.attendanceFormDirty = true; });

    // These are window/document.body-level listeners, which - unlike the
    // per-radio and per-form listeners above - are never torn down when
    // this partial gets swapped out for a new date, since window and body
    // themselves are never replaced. Without this guard, changing the date
    // N times would attach N copies of each listener; a teacher hitting
    // Back with unsaved changes would then see the "Leave anyway?"
    // confirm() dialog once per accumulated popstate listener.
    if (!window._attendanceFormHandlersAttached) {
        window._attendanceFormHandlersAttached = true;
        window.addEventListener('beforeunload', e => { if (window.attendanceFormDirty) e.preventDefault(); });
        window.addEventListener('popstate', () => {
            if (window.attendanceFormDirty && !confirm('You have unsaved attendance. Leave anyway?')) {
                history.pushState(null, '', location.href);
            }
        });
        document.body.addEventListener('htmx:afterRequest', e => {
            if (e.detail.successful) window.attendanceFormDirty = false;
        });
    }

    // Double-submit prevention
    let isSubmitting = false;
    form.addEventListener('submit', function (e) {
        if (isSubmitting) { e.preventDefault(); return false; }
        isSubmitting = true;
        form.querySelectorAll('button[type="submit"]').forEach(btn => { btn.disabled = true; });
        setTimeout(() => {
            isSubmitting = false;
            form.querySelectorAll('button[type="submit"]').forEach(btn => { btn.disabled = false; });
        }, 10000);
    });
})();
