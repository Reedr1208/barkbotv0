// ─── Browse All Dogs ────────────────────────────────────────────────
// Tile grid view showing all dogs matching current preferences

const browseGrid = document.getElementById('browseGrid');
const browseCount = document.getElementById('browseCount');
const browseAdjustPrefs = document.getElementById('browseAdjustPrefs');
const browseLoading = document.getElementById('browseLoading');
const browseEmpty = document.getElementById('browseEmpty');

// Track whether we're currently in browse mode (used by preferences.js)
let isBrowseMode = false;

async function openBrowseView(returnTo) {
  isBrowseMode = true;
  switchView('browse');

  // Show loading state
  if (browseGrid) browseGrid.innerHTML = '';
  if (browseLoading) browseLoading.style.display = 'flex';
  if (browseEmpty) browseEmpty.style.display = 'none';
  if (browseCount) browseCount.textContent = '';

  // Sync the browse location selector with the main one
  syncBrowseLocationSelect();

  // Build query params from current preferences
  const params = new URLSearchParams({ email: userEmail });
  if (currentPrefs.gender && currentPrefs.gender !== 'any') params.set('gender', currentPrefs.gender);
  if (currentPrefs.age_group && currentPrefs.age_group !== 'any') params.set('age_group', currentPrefs.age_group);
  if (currentPrefs.size && currentPrefs.size !== 'any') params.set('size', currentPrefs.size);
  if (currentPrefs.location && currentPrefs.location !== 'any') params.set('location', currentPrefs.location);
  if (lifestylePrefs.energy && lifestylePrefs.energy !== 'any') params.set('energy', lifestylePrefs.energy);
  if (lifestylePrefs.altered && lifestylePrefs.altered !== 'any') params.set('altered', lifestylePrefs.altered);
  if (lifestylePrefs.dogs) params.set('dogs', 'true');
  if (lifestylePrefs.houseTrained) params.set('house_trained', 'true');

  try {
    const res = await fetch(`/api/browse_dogs?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch dogs');
    const data = await res.json();

    if (browseLoading) browseLoading.style.display = 'none';

    if (!data.dogs || data.dogs.length === 0) {
      if (browseEmpty) browseEmpty.style.display = 'flex';
      if (browseCount) browseCount.textContent = '0 dogs';
      return;
    }

    if (browseCount) browseCount.textContent = `${data.total} dog${data.total !== 1 ? 's' : ''}`;

    // Render tiles
    const fragment = document.createDocumentFragment();
    for (const dog of data.dogs) {
      const tile = document.createElement('a');
      const path = dog.relative_path ? `/dogs${dog.relative_path}/${dog.animal_id}` : `/dogs/${dog.animal_id}`;
      tile.href = path;
      tile.className = 'browse-tile';
      tile.setAttribute('data-animal-id', dog.animal_id);

      const img = document.createElement('img');
      img.src = dog.image_url || 'happy_rescue_pup.png';
      img.alt = dog.name;
      img.loading = 'lazy';
      img.onerror = function() { this.src = 'happy_rescue_pup.png'; };
      tile.appendChild(img);

      const info = document.createElement('div');
      info.className = 'browse-tile-info';

      const nameEl = document.createElement('span');
      nameEl.className = 'browse-tile-name';
      nameEl.textContent = dog.name;
      info.appendChild(nameEl);

      const shelterEl = document.createElement('span');
      shelterEl.className = 'browse-tile-shelter';
      const locShort = (dog.location || '').replace(/,.*$/, '').replace(/\s*[\u{1F000}-\u{1FFFF}]/gu, '').trim();
      shelterEl.textContent = locShort ? `${dog.shelter_name} \u00B7 ${locShort}` : dog.shelter_name;
      info.appendChild(shelterEl);

      tile.appendChild(info);
      fragment.appendChild(tile);
    }
    browseGrid.appendChild(fragment);

  } catch (err) {
    console.error('Browse dogs error:', err);
    if (browseLoading) browseLoading.style.display = 'none';
    if (browseEmpty) {
      browseEmpty.style.display = 'flex';
      const emptyP = browseEmpty.querySelector('p');
      if (emptyP) emptyP.textContent = 'Something went wrong. Try again.';
    }
  }
}

function closeBrowseView() {
  isBrowseMode = false;
  switchView('app');
}

// Sync the browse location dropdown with the main header's location dropdown
function syncBrowseLocationSelect() {
  const mainSelect = document.getElementById('headerLocationSelect');
  const browseSelect = document.getElementById('browseLocationSelect');
  if (!mainSelect || !browseSelect) return;

  // Copy options from main select
  browseSelect.innerHTML = '';
  for (const opt of mainSelect.options) {
    const newOpt = document.createElement('option');
    newOpt.value = opt.value;
    newOpt.textContent = opt.textContent;
    newOpt.style.color = 'black';
    browseSelect.appendChild(newOpt);
  }
  browseSelect.value = mainSelect.value;
}

// ─── Event listeners ──────────────────────────────────────────────

// "Your Matches" button in app header → open browse view
const browseAllBtn = document.getElementById('browseAllBtn');
if (browseAllBtn) {
  browseAllBtn.addEventListener('click', () => {
    trackEvent('browse_all_clicked');
    openBrowseView();
  });
}

// "Meet One" button in browse header → go back to single dog view
const browseMeetOneBtn = document.getElementById('browseMeetOneBtn');
if (browseMeetOneBtn) {
  browseMeetOneBtn.addEventListener('click', closeBrowseView);
}

// Bottom "Adjust Preferences" button
if (browseAdjustPrefs) {
  browseAdjustPrefs.addEventListener('click', () => openPrefModal());
}

// Empty state "Adjust Preferences" button
const browseEmptyPrefsBtn = document.getElementById('browseEmptyPrefsBtn');
if (browseEmptyPrefsBtn) {
  browseEmptyPrefsBtn.addEventListener('click', () => openPrefModal());
}

// Browse header nav buttons — wire to the same modals as app header
const browseAboutBtn = document.getElementById('browseAboutBtn');
if (browseAboutBtn) browseAboutBtn.addEventListener('click', () => {
  const modal = document.getElementById('aboutModal');
  if (modal) { modal.classList.add('active'); modal.setAttribute('aria-hidden', 'false'); }
});

const browseContactBtn = document.getElementById('browseContactBtn');
if (browseContactBtn) browseContactBtn.addEventListener('click', () => {
  if (typeof openContactModal === 'function') openContactModal();
});

const browsePrefBtn = document.getElementById('browsePrefBtn');
if (browsePrefBtn) browsePrefBtn.addEventListener('click', () => openPrefModal());

const browseSearchBtn = document.getElementById('browseSearchBtn');
if (browseSearchBtn) browseSearchBtn.addEventListener('click', () => {
  if (typeof openSearchOverlay === 'function') openSearchOverlay();
});

const browseSavedBtn = document.getElementById('browseSavedBtn');
if (browseSavedBtn) browseSavedBtn.addEventListener('click', () => {
  if (typeof openSavedModal === 'function') openSavedModal();
});

// Show the My Dogs button in browse header if user has saved dogs
function updateBrowseSavedBtn() {
  const mainSavedBtn = document.getElementById('savedNavBtn');
  const bSavedBtn = document.getElementById('browseSavedBtn');
  if (mainSavedBtn && bSavedBtn) {
    bSavedBtn.style.display = mainSavedBtn.style.display;
  }
}

// Browse location selector — change location and refresh browse
const browseLocationSelect = document.getElementById('browseLocationSelect');
if (browseLocationSelect) {
  browseLocationSelect.addEventListener('change', (e) => {
    const val = e.target.value;
    // Sync to main header select
    const mainSelect = document.getElementById('headerLocationSelect');
    if (mainSelect) mainSelect.value = val;
    // Update prefs
    currentPrefs.location = val === 'any' ? 'any' : browseLocationSelect.options[browseLocationSelect.selectedIndex].textContent.trim();
    localStorage.setItem('chattyhound_prefs', JSON.stringify(currentPrefs));
    // Refresh browse
    openBrowseView();
  });
}
