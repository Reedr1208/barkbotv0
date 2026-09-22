// ─── Preferences & UI Controls ──────────────────────────────────────────────
// Preference wizard, save/reset preferences (guest-only, no sign-in)

const stickyInfoBtn = document.getElementById('stickyInfoBtn');
if (stickyInfoBtn) {
  stickyInfoBtn.addEventListener('click', () => {
    const trustBanner = document.getElementById('chatTrustBanner');
    const introCard = document.getElementById('chatIntroCard');
    if (trustBanner && introCard) {
      const isHidden = trustBanner.style.display === 'none';
      trustBanner.style.display = isHidden ? 'flex' : 'none';
      introCard.style.display = isHidden ? 'block' : 'none';
      if (isHidden) {
        const chatSec = document.getElementById('chatSection');
        if (chatSec) chatSec.scrollIntoView({ behavior: 'smooth' });
      }
    }
  });
}

const footerOverlay = document.getElementById('footerOverlay');
if (footerOverlay) {
  footerOverlay.addEventListener('click', (e) => {
    e.preventDefault();
    enterChatMode();
  });
}

const stickyChatBtn = document.getElementById('stickyChatBtn');
if (stickyChatBtn) {
  stickyChatBtn.addEventListener('click', () => {
    enterChatMode();
  });
}

const stickyBackBtn = document.getElementById('stickyBackBtn');
if (stickyBackBtn) {
  stickyBackBtn.addEventListener('click', () => {
    exitChatMode();
  });
}

const stickyNextBtn = document.getElementById('stickyNextBtn');
if (stickyNextBtn) {
  stickyNextBtn.addEventListener('click', () => {
    fetchRandomDog();
  });
}

// Anchor smooth-scrolling ask CTA
const askBtn = document.getElementById('askBtn');
if (askBtn) {
  askBtn.addEventListener('click', (e) => {
    e.preventDefault();
    if (window.innerWidth >= 800) {
      enterChatMode();
    } else {
      const chatSec = document.getElementById('chatSection');
      if (chatSec) {
        chatSec.scrollIntoView({ behavior: 'smooth' });
        enterChatMode();
      }
    }
  });
}

if (paccLink) {
  paccLink.addEventListener('click', () => {
    trackEvent('shelter_link_clicked', {
      dog_name: currentDogName,
      animal_id: currentAnimalId,
      shelter_name: currentDogData?.shelter_name || '',
      source: 'dog_card'
    });
  });
}

// Suggested Prompts document-level click handler (Deprecated: listeners bound directly to buttons)


// About Modal Controllers
const aboutModal = document.getElementById('aboutModal');
const aboutBtn = document.getElementById('aboutBtn');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalStartBtn = document.getElementById('modalStartBtn');

function openModal() {
  if (aboutModal) {
    aboutModal.classList.add('active');
    aboutModal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  if (modalStartBtn) {
    modalStartBtn.focus();
  }
}

function closeModal() {
  if (document.activeElement && aboutModal && aboutModal.contains(document.activeElement)) {
    document.activeElement.blur();
  }
  if (aboutModal) {
    aboutModal.classList.remove('active');
    aboutModal.setAttribute('aria-hidden', 'true');
  }
  document.body.style.overflow = '';
  localStorage.setItem('chattyhound_visited', 'true');
  if (aboutBtn) {
    aboutBtn.focus();
  }
}

if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
if (modalStartBtn) modalStartBtn.addEventListener('click', closeModal);

if (aboutModal) {
  aboutModal.addEventListener('click', (e) => {
    if (e.target === aboutModal) {
      closeModal();
    }
  });
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && aboutModal && aboutModal.classList.contains('active')) {
    closeModal();
  }
});

if (aboutBtn) {
  aboutBtn.addEventListener('click', openModal);
}

// Preferences Modal Elements
const prefModal = document.getElementById('prefModal');
const prefBtn = document.getElementById('prefBtn');
const prefBtnText = document.getElementById('prefBtnText');
const prefCloseBtn = document.getElementById('prefCloseBtn');
const prefLoggedInState = document.getElementById('prefLoggedInState');

const savePrefBtn = document.getElementById('savePrefBtn');

// currentPrefs, lifestylePrefs declared in state.js
// switchView, enterChatMode, exitChatMode declared in ui.js

// No wizard steps — single flat panel

const prefSkipBtn = document.getElementById('prefSkipBtn');
if (prefSkipBtn) {
  prefSkipBtn.addEventListener('click', () => {
    closePrefModal();
    if (window.__CH_INTERRUPTED_NEXT_DOG__) {
      window.__CH_INTERRUPTED_NEXT_DOG__ = false;
      fetchRandomDog();
    } else if (document.getElementById('landingView').classList.contains('active')) {
      switchView('app');
      fetchRandomDog();
    }
  });
}

function updateProfileButton() {
  if (prefBtnText) {
    prefBtnText.textContent = 'Fit';
  }
}

function getEffectiveLocation() {
  // 1. If a location preference is already set, use it
  if (currentPrefs.location && currentPrefs.location !== 'any') {
    return currentPrefs.location;
  }

  // 2. Check the header dropdown for the active session location
  const headerSelect = document.getElementById('headerLocationSelect');
  if (headerSelect && headerSelect.value && headerSelect.value !== 'any') {
    if (headerSelect.value === 'all') return 'all';
    const locations = window.__CH_LOCATIONS_DATA__ || [];
    const locObj = locations.find(l => l.relative_path === headerSelect.value);
    if (locObj) return locObj.display_name;
  }

  // 3. Compute closest location from user coordinates (same logic as random_dog.py)
  if (userCoords) {
    const regionCoords = {
      'Tucson, AZ 🌵': { lat: 32.2226, lon: -110.9747 },
      'Phoenix, AZ 🌵': { lat: 33.4484, lon: -112.0740 },
      'Chicago, IL 🧁': { lat: 41.8781, lon: -87.6298 },
      'New York, NY 🗽': { lat: 40.7128, lon: -74.0060 },
      'Los Angeles, CA 🌴': { lat: 34.0522, lon: -118.2437 },
      'Houston, TX 🤠': { lat: 29.7604, lon: -95.3698 },
      'San Antonio, TX 🤠': { lat: 29.4241, lon: -98.4936 },
      'Dallas, TX 🤠': { lat: 32.7767, lon: -96.7970 },
      'Philadelphia, PA 🫡': { lat: 39.9526, lon: -75.1652 },
      'San Diego, CA 🏖️': { lat: 32.7157, lon: -117.1611 },
      'San Francisco, CA 🌁': { lat: 37.7749, lon: -122.4194 },
      'Jacksonville, FL 🌴': { lat: 30.3322, lon: -81.6557 },
    };
    const locations = window.__CH_LOCATIONS_DATA__ || [];
    let bestDist = Infinity;
    let bestName = 'all';
    for (const loc of locations) {
      const coords = Object.entries(regionCoords).find(([name]) =>
        loc.display_name.replace(/\s*[\u{1F000}-\u{1FFFF}]/gu, '').trim() === name.replace(/\s*[\u{1F000}-\u{1FFFF}]/gu, '').trim()
      );
      if (coords) {
        const c = coords[1];
        const dist = Math.pow(userCoords.lat - c.lat, 2) + Math.pow(userCoords.lon - c.lon, 2);
        if (dist < bestDist) {
          bestDist = dist;
          bestName = loc.display_name;
        }
      }
    }
    return bestName;
  }

  return 'all';
}

function openPrefModal() {
  if (!prefModal) return;
  prefModal.classList.add('active');
  prefModal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';

  // Always show the wizard directly (no login gate)
  if (prefLoggedInState) prefLoggedInState.style.display = 'block';

  // Compute effective location default
  const effectiveLocation = getEffectiveLocation();

  // Setup initial button states from current preferences
  setupSelectorButtons('prefGenderGroup', currentPrefs.gender);
  setupSelectorButtons('prefAgeGroup', currentPrefs.age_group);
  setupSelectorButtons('prefSizeGroup', currentPrefs.size);
  setupSelectorButtons('prefLocationGroup', effectiveLocation);
  setupSelectorButtons('prefEnergyGroup', lifestylePrefs.energy || 'any');
  setupSelectorButtons('prefAlteredGroup', lifestylePrefs.altered || 'any');

  // Setup toggle badge states
  setupToggleBadge('prefOptDogs', lifestylePrefs.dogs);
  setupToggleBadge('prefOptHouseTrained', lifestylePrefs.houseTrained);


}

function closePrefModal() {
  if (document.activeElement && prefModal && prefModal.contains(document.activeElement)) {
    document.activeElement.blur();
  }
  if (prefModal) {
    prefModal.classList.remove('active');
    prefModal.setAttribute('aria-hidden', 'true');
  }
  document.body.style.overflow = '';
  if (prefBtn) {
    prefBtn.focus();
  }

}

function setupSelectorButtons(groupId, activeValue) {
  const container = document.getElementById(groupId);
  if (!container) return;
  const buttons = container.querySelectorAll('.pref-btn');
  buttons.forEach(btn => {
    if (btn.getAttribute('data-value') === activeValue) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

function setupToggleBadge(elementId, isActive) {
  const btn = document.getElementById(elementId);
  if (btn) {
    btn.setAttribute('data-active', isActive ? 'true' : 'false');
    btn.classList.toggle('active', isActive);
  }
}

// Handle Selector Group Clicks
function handleSelectorClick(e) {
  const btn = e.target.closest('.pref-btn');
  if (!btn) return;

  // Skip advanced multi-toggle badges
  if (btn.id && btn.id.startsWith('prefOpt')) return;

  const container = btn.parentElement;
  if (!container) return;
  container.querySelectorAll('.pref-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

const prefGenderGroup = document.getElementById('prefGenderGroup');
const prefAgeGroup = document.getElementById('prefAgeGroup');
const prefSizeGroup = document.getElementById('prefSizeGroup');
const prefLocationGroup = document.getElementById('prefLocationGroup');
const prefEnergyGroup = document.getElementById('prefEnergyGroup');
const prefAlteredGroup = document.getElementById('prefAlteredGroup');

if (prefGenderGroup) prefGenderGroup.addEventListener('click', handleSelectorClick);
if (prefAgeGroup) prefAgeGroup.addEventListener('click', handleSelectorClick);
if (prefSizeGroup) prefSizeGroup.addEventListener('click', handleSelectorClick);
if (prefLocationGroup) prefLocationGroup.addEventListener('click', handleSelectorClick);
if (prefEnergyGroup) prefEnergyGroup.addEventListener('click', handleSelectorClick);
if (prefAlteredGroup) prefAlteredGroup.addEventListener('click', handleSelectorClick);

// Bind custom toggle badges
const lifestyleButtons = [
  { id: 'prefOptDogs', key: 'dogs' },
  { id: 'prefOptHouseTrained', key: 'houseTrained' }
];

lifestyleButtons.forEach(item => {
  const btn = document.getElementById(item.id);
  if (btn) {
    btn.addEventListener('click', () => {
      const isActive = btn.getAttribute('data-active') === 'true';
      btn.setAttribute('data-active', !isActive);
      btn.classList.toggle('active', !isActive);
      lifestylePrefs[item.key] = !isActive;
      localStorage.setItem('chattyhound_lifestyle_prefs', JSON.stringify(lifestylePrefs));
    });
  }
});

// Save preferences (localStorage only — no backend for guests)
async function handleSavePreferences() {
  const genderActive = document.getElementById('prefGenderGroup').querySelector('.pref-btn.active');
  const ageActive = document.getElementById('prefAgeGroup').querySelector('.pref-btn.active');
  const sizeActive = document.getElementById('prefSizeGroup').querySelector('.pref-btn.active');
  const locationActive = document.getElementById('prefLocationGroup').querySelector('.pref-btn.active');

  const gender = genderActive ? genderActive.getAttribute('data-value') : 'any';
  const age_group = ageActive ? ageActive.getAttribute('data-value') : 'any';
  const size = sizeActive ? sizeActive.getAttribute('data-value') : 'any';
  const location = locationActive ? locationActive.getAttribute('data-value') : 'any';

  // Save advanced lifestyle preferences
  const energyActive = document.getElementById('prefEnergyGroup').querySelector('.pref-btn.active');
  const alteredActive = document.getElementById('prefAlteredGroup').querySelector('.pref-btn.active');
  lifestylePrefs.energy = energyActive ? energyActive.getAttribute('data-value') : 'any';
  lifestylePrefs.altered = alteredActive ? alteredActive.getAttribute('data-value') : 'any';
  localStorage.setItem('chattyhound_lifestyle_prefs', JSON.stringify(lifestylePrefs));

  savePrefBtn.disabled = true;
  savePrefBtn.textContent = 'Saving...';

  currentPrefs = { gender, age_group, size, location };
  localStorage.setItem('chattyhound_prefs', JSON.stringify(currentPrefs));

  // Sync to backend (non-blocking)
  fetch('/api/save_preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: userEmail, preferences: { gender, age_group, size, location } })
  }).catch(() => {});

  // Sync header location dropdown with preference center selection
  const headerSelect = document.getElementById('headerLocationSelect');
  if (headerSelect && window.__CH_LOCATIONS_DATA__) {
    if (location === 'any' || location === 'all') {
      headerSelect.value = location === 'any' ? 'all' : 'all';
    } else {
      const locObj = window.__CH_LOCATIONS_DATA__.find(l => l.display_name === location);
      if (locObj) headerSelect.value = locObj.relative_path;
    }
  }

  closePrefModal();
  trackEvent('preferences_saved', { gender, age_group, size, location, ...lifestylePrefs });

  // If in browse mode, stay in browse and refresh results; otherwise go to app view
  if (typeof isBrowseMode !== 'undefined' && isBrowseMode) {
    openBrowseView();
  } else {
    switchView('app');
    fetchRandomDog();
  }

  savePrefBtn.disabled = false;
  savePrefBtn.innerHTML = 'Save Selections ✨';
}

async function resetPreferences() {
  // 1. Clear local state
  currentPrefs = { gender: 'any', age_group: 'any', size: 'any', location: 'any' };
  lifestylePrefs = {
    energy: 'any',
    altered: 'any',
    dogs: false,
    houseTrained: false
  };

  // 2. Write to localStorage
  localStorage.setItem('chattyhound_lifestyle_prefs', JSON.stringify(lifestylePrefs));
  localStorage.setItem('chattyhound_prefs', JSON.stringify(currentPrefs));

  // Sync reset to backend (non-blocking)
  fetch('/api/save_preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: userEmail, preferences: { gender: 'any', age_group: 'any', size: 'any', location: 'any' } })
  }).catch(() => {});

  // 3. Update the selectors visually so that if user opens preferences again, it is correctly reset
  setupSelectorButtons('prefGenderGroup', 'any');
  setupSelectorButtons('prefAgeGroup', 'any');
  setupSelectorButtons('prefSizeGroup', 'any');
  setupSelectorButtons('prefLocationGroup', 'any');
  setupSelectorButtons('prefEnergyGroup', 'any');
  setupSelectorButtons('prefAlteredGroup', 'any');
  lifestyleButtons.forEach(item => setupToggleBadge(item.id, false));



  // 4. Trigger a fresh match load
  await fetchRandomDog();
}

// Event listeners
const emptyStateResetBtn = document.getElementById('emptyStateResetBtn');
if (emptyStateResetBtn) {
  emptyStateResetBtn.addEventListener('click', openPrefModal);
}
const emptyStateAllBtn = document.getElementById('emptyStateAllBtn');
if (emptyStateAllBtn) {
  emptyStateAllBtn.addEventListener('click', resetPreferences);
}
if (prefBtn) prefBtn.addEventListener('click', openPrefModal);
if (prefCloseBtn) prefCloseBtn.addEventListener('click', closePrefModal);

if (prefModal) {
  prefModal.addEventListener('click', (e) => {
    if (e.target === prefModal) closePrefModal();
  });
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (prefModal && prefModal.classList.contains('active')) {
      closePrefModal();
    }
    if (savedModal && savedModal.classList.contains('active')) {
      closeSavedModal();
    }
  }
});

if (savePrefBtn) {
  savePrefBtn.addEventListener('click', handleSavePreferences);
}

