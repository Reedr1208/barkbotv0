// ─── Location & Shelter Filters ─────────────────────────────────────────────
// Single source of truth for the Location + Shelter filter:
//   • state  — currentPrefs.location (display_name | 'all' | 'any') + currentPrefs.shelter (shelter_id | null)
//   • rules  — cascading transitions from WorkingFiles/ChattyHound-Location-and-Shelter-Filters.md
//   • UI     — header/browse filter chips + one shared picker panel
//              (anchored popover on desktop, bottom sheet on narrow screens)
//   • URLs   — /dogs/<loc>[/<shelterSlug>][/<dogId>] in the address bar; dog share links stay location-only
//
// Shelter data (id, name, slug, location) comes from /api/locations — the same shelters
// table that drives dog listings.

window.__CH_SHELTERS_DATA__ = window.__CH_SHELTERS_DATA__ || [];

const CHF_DESKTOP_MIN_WIDTH = 800;

// ─── Data helpers ───────────────────────────────────────────────────────────

function chfLocations() { return window.__CH_LOCATIONS_DATA__ || []; }
function chfShelters() { return window.__CH_SHELTERS_DATA__ || []; }
function chfIsAll(loc) { return !loc || loc === 'all' || loc === 'any'; }

function chfStripEmoji(s) {
  return String(s || '')
    .replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}\u{20E3}]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function chfLocationPlain(name) { return chfIsAll(name) ? 'All locations' : chfStripEmoji(name); }
function chfCity(name) { return chfStripEmoji(name).replace(/,.*$/, '').trim(); }

function findLocationByName(name) {
  if (chfIsAll(name)) return null;
  const clean = chfStripEmoji(name).toLowerCase();
  return chfLocations().find(l => l.display_name === name)
    || chfLocations().find(l => chfStripEmoji(l.display_name).toLowerCase() === clean)
    || null;
}

function findLocationByPath(path) {
  if (!path) return null;
  const p = ('/' + String(path).replace(/^\/+/, '')).toLowerCase();
  return chfLocations().find(l => (l.relative_path || '').toLowerCase() === p) || null;
}

function findShelterById(id) {
  if (!id) return null;
  const want = String(id).toUpperCase();
  return chfShelters().find(s => String(s.shelter_id).toUpperCase() === want) || null;
}

function findShelterBySlug(locPath, slug) {
  if (!locPath || !slug) return null;
  const p = ('/' + String(locPath).replace(/^\/+/, '')).toLowerCase();
  const sl = String(slug).toLowerCase();
  return chfShelters().find(s => (s.relative_path || '').toLowerCase() === p && s.slug === sl) || null;
}

function isShelterSlugPath(locSeg, slugSeg) {
  if (!locSeg || !slugSeg) return false;
  if (window.__CH_INITIAL_LOCATION__ === '/' + locSeg && window.__CH_INITIAL_SHELTER__ === slugSeg) return true;
  return !!findShelterBySlug('/' + locSeg, slugSeg);
}

function isLocationPathSegment(seg) {
  if (!seg) return false;
  if (seg === 'alldogs') return true;
  if (window.__CH_INITIAL_LOCATION__ === '/' + seg) return true;
  return !!findLocationByPath('/' + seg);
}

function chfSortByName(list) {
  return list.slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
}

function sheltersInLocation(locName) {
  const loc = findLocationByName(locName);
  if (!loc) return [];
  return chfSortByName(chfShelters().filter(s => s.location === loc.display_name));
}

// ─── State ──────────────────────────────────────────────────────────────────

function getFilterState() {
  return {
    location: chfIsAll(currentPrefs.location) ? 'all' : currentPrefs.location,
    shelter: currentPrefs.shelter || null,
  };
}

// Enforce consistency: a shelter implies its location; unknown shelters fall back to the location scope.
function normalizeFilterState(s) {
  let location = chfIsAll(s && s.location) ? 'all' : s.location;
  let shelter = (s && s.shelter) || null;
  const haveShelterData = chfShelters().length > 0;
  const haveLocationData = chfLocations().length > 0;

  if (shelter && haveShelterData) {
    const sh = findShelterById(shelter);
    if (!sh) shelter = null;
    else { shelter = sh.shelter_id; location = sh.location; }
  }
  if (location !== 'all' && haveLocationData) {
    const loc = findLocationByName(location);
    location = loc ? loc.display_name : 'all';
    if (!loc) shelter = null;
  }
  return { location, shelter };
}

function dogMatchesFilter(dog, state) {
  if (!dog || !dog.shelter_id) return false;
  const st = state || getFilterState();
  if (st.shelter) return String(dog.shelter_id).toUpperCase() === String(st.shelter).toUpperCase();
  if (chfIsAll(st.location)) return true;
  const loc = findLocationByName(st.location);
  return !!(loc && (loc.shelter_ids || []).includes(dog.shelter_id));
}

function describeShelterScope(state) {
  const st = state || getFilterState();
  if (st.shelter) {
    const sh = findShelterById(st.shelter);
    return sh ? sh.name : 'Selected shelter';
  }
  return chfIsAll(st.location) ? 'All shelters everywhere' : `All shelters in ${chfLocationPlain(st.location)}`;
}

/**
 * Apply a new Location/Shelter state.
 * opts.source  — analytics source label ('header' | 'browse' | 'prefs' | 'route' | 'dog' | 'detect' | 'init')
 * opts.apply   — refresh results (dog / browse grid) + push a history entry
 * opts.persist — write to localStorage (default true)
 * opts.track   — fire analytics events (default true)
 */
function setFilterState(next, opts = {}) {
  const prev = getFilterState();
  const state = normalizeFilterState(next);

  // Preserve the "never chosen" marker ('any') unless the user actually picked something.
  const keepAny = chfIsAll(state.location) && currentPrefs.location === 'any' && opts.source !== 'header' && opts.source !== 'browse' && opts.source !== 'prefs';
  currentPrefs.location = keepAny ? 'any' : state.location;
  currentPrefs.shelter = state.shelter || null;
  if (opts.persist !== false) localStorage.setItem('chattyhound_prefs', JSON.stringify(currentPrefs));

  renderFilterControls();

  const locChanged = prev.location !== state.location;
  const shelterChanged = prev.shelter !== state.shelter;
  if ((locChanged || shelterChanged) && opts.track !== false && typeof trackEvent === 'function') {
    if (locChanged) trackEvent('location_changed', { from_location: prev.location, to_location: state.location, source: opts.source || '' });
    if (shelterChanged || locChanged) {
      trackEvent('shelter_changed', {
        from_shelter: prev.shelter || (chfIsAll(prev.location) ? 'all_everywhere' : 'all_in_location'),
        to_shelter: state.shelter || (chfIsAll(state.location) ? 'all_everywhere' : 'all_in_location'),
        location: state.location,
        source: opts.source || '',
      });
    }
  }

  if ((locChanged || shelterChanged) && opts.apply) applyFilterChange(state);
  return state;
}

// Refresh results after a live filter change (SPA — no full page reload).
function applyFilterChange(state) {
  const inBrowse = typeof isBrowseMode !== 'undefined' && isBrowseMode;
  const appState = document.body.dataset.chAppState || '';
  const keepDog = !inBrowse && currentDogData && appState === 'dog_loaded' && dogMatchesFilter(currentDogData, state);

  const url = buildFilterUrl(state, keepDog ? currentDogData.animal_id : null);
  try { history.pushState({ filter: state }, '', url); } catch (_) {}

  if (inBrowse) {
    openBrowseView();
    return;
  }
  if (keepDog) {
    if (typeof updateDocumentMetaForDog === 'function') updateDocumentMetaForDog(currentDogData);
    return;
  }
  fetchRandomDog();
}

// ─── URLs ───────────────────────────────────────────────────────────────────

function getFilterLocationPath(state) {
  const st = state || getFilterState();
  if (chfIsAll(st.location)) return '/alldogs';
  const loc = findLocationByName(st.location);
  return loc ? loc.relative_path : '';
}

function getFilterShelterSlug(state) {
  const st = state || getFilterState();
  const sh = st.shelter ? findShelterById(st.shelter) : null;
  return sh ? sh.slug : '';
}

// Address-bar path: /dogs/<loc>[/<shelterSlug>][/<dogId>]
// (When no location was ever chosen — currentPrefs.location === 'any' — keep the legacy /dogs/<id>.)
function buildFilterUrl(state, dogId) {
  const unset = !state && currentPrefs.location === 'any';
  const st = state || getFilterState();
  let path = '/dogs' + (unset ? '' : getFilterLocationPath(st));
  const slug = getFilterShelterSlug(st);
  if (slug && !chfIsAll(st.location)) path += '/' + slug;
  if (dogId) path += '/' + encodeURIComponent(dogId);
  return path === '/dogs' ? '/' : path;
}

// Shareable link for the current scope: /<loc>/<shelterSlug>, /<loc>, or /dogs/alldogs
function buildShareableScopeUrl(state) {
  const st = state || getFilterState();
  if (chfIsAll(st.location)) return CH_CANONICAL_ORIGIN + '/dogs/alldogs';
  const locPath = getFilterLocationPath(st);
  const slug = getFilterShelterSlug(st);
  return CH_CANONICAL_ORIGIN + (locPath || '') + (slug ? '/' + slug : '');
}

// Parse location/shelter scope from a path. Returns null when the path carries no scope.
function parseFilterFromPath(pathname) {
  const segs = String(pathname || '').split('/').filter(Boolean).map(s => { try { return decodeURIComponent(s); } catch (_) { return s; } });
  if (!segs.length) return null;
  let rest = segs;
  if (segs[0] === 'dogs') rest = segs.slice(1);
  else if (segs.length > 2) return null;
  if (!rest.length) return null;

  if (rest[0] === 'alldogs') return { location: 'all', shelter: null };
  const loc = findLocationByPath('/' + rest[0]);
  if (!loc) return null;
  const sh = rest[1] ? findShelterBySlug(loc.relative_path, rest[1]) : null;
  return { location: loc.display_name, shelter: sh ? sh.shelter_id : null };
}

// Apply the scope encoded in the current URL (used on back/forward). No history push, no refetch.
function applyFilterFromPath(pathname) {
  const parsed = parseFilterFromPath(pathname || window.location.pathname);
  if (parsed) setFilterState(parsed, { source: 'route', track: false, persist: false });
}

// Initial state once /api/locations has loaded: URL scope wins, else stored preferences.
function initFilterState() {
  const initLoc = window.__CH_INITIAL_LOCATION__ || null;
  if (initLoc) {
    let state;
    if (initLoc === '/alldogs') {
      state = { location: 'all', shelter: null };
    } else {
      const loc = findLocationByPath(initLoc);
      state = { location: loc ? loc.display_name : 'all', shelter: null };
      const sh = window.__CH_INITIAL_SHELTER__ ? findShelterBySlug(initLoc, window.__CH_INITIAL_SHELTER__) : null;
      if (sh) state.shelter = sh.shelter_id;
    }
    setFilterState(state, { source: 'init', track: false, persist: false });
    if (initLoc === '/alldogs') currentPrefs.location = 'all';
    return;
  }
  const stored = { location: currentPrefs.location, shelter: currentPrefs.shelter || null };
  const norm = normalizeFilterState(stored);
  const changed = (norm.shelter || null) !== (stored.shelter || null) || (!chfIsAll(stored.location) && norm.location !== stored.location);
  setFilterState(stored, { source: 'init', track: false, persist: changed });
}

// ─── Chips (header + browse) ────────────────────────────────────────────────

function renderFilterControls() {
  const st = getFilterState();
  const locText = chfIsAll(st.location) ? 'All locations 🌎' : st.location;
  const sh = st.shelter ? findShelterById(st.shelter) : null;
  const shelterText = sh ? sh.name : 'All shelters';
  const scopeText = describeShelterScope(st);
  const aria = `Filters. Location: ${chfLocationPlain(st.location)}. Shelter: ${scopeText}. Change location or shelter`;

  document.querySelectorAll('[data-ch-filter-chip]').forEach(chip => {
    const locEl = chip.querySelector('.chf-chip__loc');
    const shEl = chip.querySelector('.chf-chip__shelter');
    if (locEl) locEl.textContent = locText;
    if (shEl) shEl.textContent = shelterText;
    chip.setAttribute('aria-label', aria);
    chip.title = `${chfLocationPlain(st.location)} · ${scopeText}`;
    chip.classList.toggle('is-scoped', !chfIsAll(st.location));
    chip.classList.toggle('has-shelter', !!sh);
  });

  if (chfPanel.el && chfPanel.open && chfPanel.mode === 'live') {
    chfPanel.state = st;
    renderFilterPanel();
  }
}

// ─── Shared picker panel ────────────────────────────────────────────────────

const chfPanel = {
  el: null, backdrop: null, open: false, mode: 'live',
  state: { location: 'all', shelter: null }, onChange: null,
  trigger: null, query: '', activeId: null, source: 'header',
};

function chfEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function chfFold(s) {
  return String(s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function chfHighlight(text, query) {
  if (!query) return chfEsc(text);
  const i = chfFold(text).indexOf(chfFold(query));
  if (i < 0) return chfEsc(text);
  return chfEsc(text.slice(0, i)) + '<mark>' + chfEsc(text.slice(i, i + query.length)) + '</mark>' + chfEsc(text.slice(i + query.length));
}

function ensureFilterPanel() {
  if (chfPanel.el) return chfPanel.el;

  const backdrop = document.createElement('div');
  backdrop.className = 'chf-backdrop';
  backdrop.hidden = true;
  backdrop.addEventListener('click', () => closeFilterPanel());

  const el = document.createElement('div');
  el.className = 'chf-panel';
  el.id = 'chFilterPanel';
  el.hidden = true;
  el.tabIndex = -1;
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'chfTitle');
  el.setAttribute('aria-describedby', 'chfSub');
  el.innerHTML = `
    <div class="chf-grab" aria-hidden="true"></div>
    <div class="chf-head">
      <div class="chf-head-text">
        <h2 class="chf-title" id="chfTitle">Where should we look?</h2>
        <p class="chf-sub" id="chfSub">Pick a location, then narrow it to one shelter if you like.</p>
      </div>
      <button type="button" class="chf-close" id="chfCloseBtn" aria-label="Close filters">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>
    <div class="chf-body">
      <div class="chf-field">
        <label class="chf-label" for="chfLocation"><span aria-hidden="true">📍</span> Location</label>
        <div class="chf-select-wrap">
          <select id="chfLocation" class="chf-select"></select>
        </div>
      </div>
      <div class="chf-field chf-field--shelter">
        <label class="chf-label" for="chfSearch" id="chfShelterLabel"><span aria-hidden="true">🏠</span> Shelter</label>
        <div class="chf-search">
          <svg class="chf-search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
          <input id="chfSearch" class="chf-search-input" type="text" role="combobox"
            aria-autocomplete="list" aria-expanded="true" aria-controls="chfList" aria-describedby="chfSearchHint"
            placeholder="Search shelters or cities" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="done">
          <button type="button" class="chf-search-clear" id="chfSearchClear" aria-label="Clear shelter search" hidden>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <p class="chf-sr-only" id="chfSearchHint">Type to filter shelters. Use the up and down arrow keys to move through choices and Enter to select.</p>
        <div class="chf-list" id="chfList" role="listbox" aria-labelledby="chfShelterLabel"></div>
      </div>
    </div>
    <div class="chf-foot" id="chfFoot">
      <button type="button" class="chf-copy" id="chfCopyBtn">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5"/></svg>
        <span id="chfCopyText">Copy link</span>
      </button>
    </div>
    <div class="chf-sr-only" id="chfLive" aria-live="polite" aria-atomic="true"></div>
  `;

  document.body.appendChild(backdrop);
  document.body.appendChild(el);
  chfPanel.el = el;
  chfPanel.backdrop = backdrop;

  el.querySelector('#chfCloseBtn').addEventListener('click', () => closeFilterPanel());
  el.querySelector('#chfLocation').addEventListener('change', (e) => {
    chfCommit({ location: e.target.value, shelter: null }, { close: false });
  });

  const search = el.querySelector('#chfSearch');
  search.addEventListener('input', () => {
    chfPanel.query = search.value;
    chfPanel.activeId = null;
    renderFilterPanel();
    const firstShelter = chfVisibleOptions().find(o => o.dataset.kind === 'shelter');
    if (chfPanel.query && firstShelter) chfSetActive(firstShelter.id);
    else chfSetActive((chfVisibleOptions().find(o => o.getAttribute('aria-selected') === 'true') || chfVisibleOptions()[0] || {}).id);
  });
  search.addEventListener('keydown', chfOnSearchKeydown);

  el.querySelector('#chfSearchClear').addEventListener('click', () => {
    search.value = '';
    chfPanel.query = '';
    renderFilterPanel();
    search.focus();
  });

  const list = el.querySelector('#chfList');
  list.addEventListener('click', (e) => {
    const opt = e.target.closest('[role="option"]');
    if (opt) chfSelectOption(opt);
  });
  list.addEventListener('mousemove', (e) => {
    const opt = e.target.closest('[role="option"]');
    if (opt && opt.id !== chfPanel.activeId) chfSetActive(opt.id, { scroll: false });
  });

  el.querySelector('#chfCopyBtn').addEventListener('click', chfCopyLink);

  el.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      e.preventDefault();
      if (document.activeElement === search && search.value) {
        search.value = '';
        chfPanel.query = '';
        renderFilterPanel();
      } else {
        closeFilterPanel();
      }
      return;
    }
    if (e.key === 'Tab') chfTrapFocus(e);
  });

  window.addEventListener('resize', () => { if (chfPanel.open) chfPosition(); });
  return el;
}

function chfIsDesktop() { return window.innerWidth >= CHF_DESKTOP_MIN_WIDTH; }

/**
 * Open the picker.
 * opts.trigger  — element that opened it (focus returns here; anchors the desktop popover)
 * opts.mode     — 'live' (apply immediately) | 'staged' (report via onChange, e.g. Fit modal)
 * opts.state    — starting state for staged mode
 * opts.onChange — staged-mode callback(state)
 * opts.focus    — 'search' | 'location'
 */
function openFilterPanel(opts = {}) {
  const el = ensureFilterPanel();
  chfPanel.mode = opts.mode || 'live';
  chfPanel.onChange = opts.onChange || null;
  chfPanel.trigger = opts.trigger || null;
  chfPanel.source = opts.source || 'header';
  chfPanel.state = normalizeFilterState(opts.state || getFilterState());
  chfPanel.query = '';
  chfPanel.activeId = null;
  el.querySelector('#chfSearch').value = '';
  el.querySelector('#chfFoot').hidden = chfPanel.mode !== 'live';
  el.classList.toggle('is-staged', chfPanel.mode !== 'live');

  renderFilterPanel();
  const selected = el.querySelector('[role="option"][aria-selected="true"]');
  chfSetActive(selected ? selected.id : null);

  chfPanel.open = true;
  el.hidden = false;
  chfPanel.backdrop.hidden = false;
  el.classList.toggle('is-sheet', !chfIsDesktop());
  chfPosition();
  requestAnimationFrame(() => {
    el.classList.add('is-open');
    chfPanel.backdrop.classList.add('is-open');
  });
  if (chfPanel.trigger) chfPanel.trigger.setAttribute('aria-expanded', 'true');

  // Desktop: straight into type-ahead. Touch/narrow: focus the dialog (avoids popping the keyboard).
  const focusTarget = opts.focus === 'location'
    ? el.querySelector('#chfLocation')
    : (chfIsDesktop() ? el.querySelector('#chfSearch') : el);
  setTimeout(() => { try { focusTarget.focus({ preventScroll: true }); } catch (_) { focusTarget.focus(); } }, 30);
  if (selected) setTimeout(() => selected.scrollIntoView({ block: 'nearest' }), 60);
}

function closeFilterPanel(opts = {}) {
  if (!chfPanel.el || !chfPanel.open) return;
  const el = chfPanel.el;
  chfPanel.open = false;
  el.classList.remove('is-open');
  chfPanel.backdrop.classList.remove('is-open');
  const done = () => { if (!chfPanel.open) { el.hidden = true; chfPanel.backdrop.hidden = true; } };
  setTimeout(done, 220);
  if (chfPanel.trigger) {
    chfPanel.trigger.setAttribute('aria-expanded', 'false');
    if (opts.returnFocus !== false) {
      try { chfPanel.trigger.focus({ preventScroll: true }); } catch (_) { chfPanel.trigger.focus(); }
    }
  }
}

function chfPosition() {
  const el = chfPanel.el;
  if (!el) return;
  const sheet = !chfIsDesktop();
  el.classList.toggle('is-sheet', sheet);
  if (sheet || !chfPanel.trigger) {
    el.style.top = el.style.left = el.style.right = el.style.maxHeight = el.style.width = '';
    return;
  }
  const r = chfPanel.trigger.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(400, vw - 24);
  let left = r.right - width;
  if (chfPanel.mode !== 'live') left = r.left;
  left = Math.max(12, Math.min(left, vw - width - 12));
  let top = r.bottom + 8;
  const spaceBelow = vh - top - 12;
  // Flip above the trigger if there's clearly more room there (e.g. Fit modal near the bottom).
  if (spaceBelow < 340 && r.top - 20 > spaceBelow) {
    const maxH = Math.min(560, r.top - 20);
    top = r.top - 8 - maxH;
    el.style.maxHeight = maxH + 'px';
  } else {
    el.style.maxHeight = Math.min(560, spaceBelow) + 'px';
  }
  el.style.width = width + 'px';
  el.style.left = left + 'px';
  el.style.right = 'auto';
  el.style.top = Math.max(12, top) + 'px';
}

function chfTrapFocus(e) {
  const el = chfPanel.el;
  const focusables = Array.from(el.querySelectorAll('button:not([hidden]), select, input'))
    .filter(n => !n.disabled && n.offsetParent !== null && !n.closest('[hidden]'));
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (e.shiftKey && (document.activeElement === first || document.activeElement === el)) { last.focus(); e.preventDefault(); }
  else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
}

function chfOption({ id, kind, value, icon, name, meta, selected, query }) {
  return `
    <div role="option" id="${id}" class="chf-opt chf-opt--${kind}" data-kind="${kind}" data-value="${chfEsc(value)}" aria-selected="${selected ? 'true' : 'false'}">
      <span class="chf-opt__icon" aria-hidden="true">${icon}</span>
      <span class="chf-opt__text">
        <span class="chf-opt__name">${kind === 'shelter' ? chfHighlight(name, query) : chfEsc(name)}</span>
        ${meta ? `<span class="chf-opt__meta">${kind === 'shelter' ? chfHighlight(meta, query) : chfEsc(meta)}</span>` : ''}
      </span>
      <svg class="chf-opt__check" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
    </div>`;
}

function chfGroup(id, label, optionsHtml) {
  if (!optionsHtml) return '';
  return `<div role="group" class="chf-group" aria-labelledby="${id}"><div class="chf-group-label" id="${id}" role="presentation">${chfEsc(label)}</div>${optionsHtml}</div>`;
}

function chfOptId(kind, value) {
  return 'chf-opt-' + kind + '-' + String(value || 'x').replace(/[^A-Za-z0-9_-]/g, '_');
}

function renderFilterPanel() {
  const el = chfPanel.el;
  if (!el) return;
  const st = chfPanel.state;
  const q = (chfPanel.query || '').trim();
  const fq = chfFold(q);
  const matches = (s) => !fq || chfFold(s.name).includes(fq) || chfFold(chfStripEmoji(s.location)).includes(fq) || chfFold(s.shelter_id).includes(fq);

  // Location select
  const sel = el.querySelector('#chfLocation');
  const locOpts = ['<option value="all">All locations 🌎</option>']
    .concat(chfLocations().map(l => `<option value="${chfEsc(l.display_name)}">${chfEsc(l.display_name)}</option>`));
  sel.innerHTML = locOpts.join('');
  sel.value = chfIsAll(st.location) ? 'all' : st.location;

  // Search affordances
  el.querySelector('#chfSearchClear').hidden = !q;

  // Shelter list
  const all = chfSortByName(chfShelters());
  const total = all.length;
  let html = '';
  let shown = 0;

  if (!chfIsAll(st.location)) {
    const locPlain = chfLocationPlain(st.location);
    const inLoc = all.filter(s => s.location === st.location);
    const elsewhere = all.filter(s => s.location !== st.location);
    const inLocShown = inLoc.filter(matches);
    const elsewhereShown = elsewhere.filter(matches);
    shown = inLocShown.length + elsewhereShown.length;

    html += chfOption({
      id: chfOptId('scope', 'location'), kind: 'scope-location', value: st.location, icon: '📍',
      name: `All shelters in ${locPlain}`,
      meta: `${inLoc.length} shelter${inLoc.length === 1 ? '' : 's'}`,
      selected: !st.shelter,
    });
    html += chfGroup('chf-g-in', `Shelters in ${locPlain}`, inLocShown.map(s => chfOption({
      id: chfOptId('shelter', s.shelter_id), kind: 'shelter', value: s.shelter_id, icon: '🏠',
      name: s.name, meta: '', selected: st.shelter === s.shelter_id, query: q,
    })).join(''));
    html += chfOption({
      id: chfOptId('scope', 'all'), kind: 'scope-all', value: 'all', icon: '🌎',
      name: 'All shelters everywhere',
      meta: `${total} shelters · switches to All locations`,
      selected: false,
    });
    html += chfGroup('chf-g-other', 'Shelters in other locations', elsewhereShown.map(s => chfOption({
      id: chfOptId('shelter', s.shelter_id), kind: 'shelter', value: s.shelter_id, icon: '🏠',
      name: s.name, meta: chfLocationPlain(s.location), selected: st.shelter === s.shelter_id, query: q,
    })).join(''));
  } else {
    const allShown = all.filter(matches);
    shown = allShown.length;
    html += chfOption({
      id: chfOptId('scope', 'all'), kind: 'scope-all', value: 'all', icon: '🌎',
      name: 'All shelters everywhere', meta: `${total} shelters`, selected: !st.shelter,
    });
    html += chfGroup('chf-g-all', 'All shelters', allShown.map(s => chfOption({
      id: chfOptId('shelter', s.shelter_id), kind: 'shelter', value: s.shelter_id, icon: '🏠',
      name: s.name, meta: chfLocationPlain(s.location), selected: st.shelter === s.shelter_id, query: q,
    })).join(''));
  }

  if (q && shown === 0) {
    html += `<div class="chf-empty" role="presentation">No shelters match “${chfEsc(q)}”.</div>`;
  }

  const list = el.querySelector('#chfList');
  list.innerHTML = html;

  if (chfPanel.activeId && !document.getElementById(chfPanel.activeId)) chfPanel.activeId = null;
  chfSetActive(chfPanel.activeId, { scroll: false });

  if (q) chfAnnounce(shown === 0 ? `No shelters match ${q}` : `${shown} shelter${shown === 1 ? '' : 's'} found`);

  // Copy-link label (live mode)
  const copyText = el.querySelector('#chfCopyText');
  if (copyText && !copyText.dataset.flash) {
    const sh = st.shelter ? findShelterById(st.shelter) : null;
    copyText.textContent = sh ? `Copy link to ${sh.name}` : (chfIsAll(st.location) ? 'Copy link to all dogs' : `Copy link to ${chfCity(st.location)} dogs`);
  }
}

function chfVisibleOptions() {
  return chfPanel.el ? Array.from(chfPanel.el.querySelectorAll('#chfList [role="option"]')) : [];
}

function chfSetActive(id, opts = {}) {
  const el = chfPanel.el;
  if (!el) return;
  chfPanel.activeId = id || null;
  const search = el.querySelector('#chfSearch');
  chfVisibleOptions().forEach(o => o.classList.toggle('is-active', o.id === id));
  if (id) {
    search.setAttribute('aria-activedescendant', id);
    if (opts.scroll !== false) {
      const node = document.getElementById(id);
      if (node) node.scrollIntoView({ block: 'nearest' });
    }
  } else {
    search.removeAttribute('aria-activedescendant');
  }
}

function chfOnSearchKeydown(e) {
  const opts = chfVisibleOptions();
  if (!opts.length) return;
  const idx = opts.findIndex(o => o.id === chfPanel.activeId);
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    chfSetActive(opts[Math.min(opts.length - 1, idx + 1)].id);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    chfSetActive(opts[Math.max(0, idx - 1)].id);
  } else if (e.key === 'PageDown') {
    e.preventDefault();
    chfSetActive(opts[Math.min(opts.length - 1, Math.max(0, idx) + 6)].id);
  } else if (e.key === 'PageUp') {
    e.preventDefault();
    chfSetActive(opts[Math.max(0, idx - 6)].id);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const active = opts[idx];
    if (active) chfSelectOption(active);
  }
}

function chfSelectOption(opt) {
  const kind = opt.dataset.kind;
  const st = chfPanel.state;
  if (kind === 'scope-location') {
    chfCommit({ location: st.location, shelter: null });
  } else if (kind === 'scope-all') {
    chfCommit({ location: 'all', shelter: null });
  } else if (kind === 'shelter') {
    const sh = findShelterById(opt.dataset.value);
    if (sh) chfCommit({ location: sh.location, shelter: sh.shelter_id });
  }
}

function chfCommit(next, opts = {}) {
  const close = opts.close !== false;
  const prev = chfPanel.state;
  const state = normalizeFilterState(next);
  chfPanel.state = state;

  if (chfPanel.mode === 'live') {
    setFilterState(state, { source: chfPanel.source, apply: true });
  } else if (typeof chfPanel.onChange === 'function') {
    chfPanel.onChange(state);
  }

  const scope = describeShelterScope(state);
  const msg = prev.location !== state.location
    ? `Location set to ${chfLocationPlain(state.location)}. Shelter: ${scope}.`
    : `Shelter: ${scope}.`;
  chfAnnounce(msg);

  if (close) {
    closeFilterPanel();
    if (chfPanel.mode === 'live' && typeof showShareToast === 'function' && !chfIsDesktop()) {
      showShareToast(state.shelter ? `Showing dogs from ${scope}` : (chfIsAll(state.location) ? 'Showing dogs everywhere' : `Showing dogs in ${chfLocationPlain(state.location)}`));
    }
  } else {
    chfPanel.query = '';
    const search = chfPanel.el.querySelector('#chfSearch');
    if (search) search.value = '';
    chfPanel.activeId = null;
    renderFilterPanel();
    const selected = chfPanel.el.querySelector('[role="option"][aria-selected="true"]');
    chfSetActive(selected ? selected.id : null);
  }
}

function chfAnnounce(msg) {
  const live = chfPanel.el && chfPanel.el.querySelector('#chfLive');
  if (!live) return;
  live.textContent = '';
  setTimeout(() => { live.textContent = msg; }, 30);
}

async function chfCopyLink() {
  const url = buildShareableScopeUrl(chfPanel.state);
  const textEl = chfPanel.el.querySelector('#chfCopyText');
  let ok = false;
  try {
    await navigator.clipboard.writeText(url);
    ok = true;
  } catch (_) {
    try {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      ok = document.execCommand('copy');
      ta.remove();
    } catch (_) {}
  }
  if (typeof trackEvent === 'function') trackEvent('filter_link_copied', { url, ok });
  if (textEl) {
    textEl.dataset.flash = '1';
    textEl.textContent = ok ? 'Link copied!' : url;
    chfPanel.el.querySelector('#chfCopyBtn').classList.toggle('is-copied', ok);
    chfAnnounce(ok ? 'Link copied to clipboard' : 'Copy this link: ' + url);
    setTimeout(() => {
      delete textEl.dataset.flash;
      chfPanel.el.querySelector('#chfCopyBtn').classList.remove('is-copied');
      renderFilterPanel();
    }, 2000);
  }
}

// ─── Wiring ─────────────────────────────────────────────────────────────────

document.querySelectorAll('[data-ch-filter-chip]').forEach(chip => {
  chip.addEventListener('click', async () => {
    if (chfPanel.open && chfPanel.trigger === chip) { closeFilterPanel(); return; }
    if (window.__CH_LOCATIONS_PROMISE__) await window.__CH_LOCATIONS_PROMISE__;
    openFilterPanel({ trigger: chip, mode: 'live', source: chip.dataset.chFilterChip || 'header' });
  });
});

renderFilterControls();
