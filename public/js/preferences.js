// ─── Preferences & Authentication ───────────────────────────────────────────
// Preference wizard, login, save/reset preferences, and sign out

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
    trackEvent('ask_cta_clicked', { dog_name: currentDogName, animal_id: currentAnimalId });
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
    trackEvent('view_profile_clicked', { dog_name: currentDogName, animal_id: currentAnimalId, url: paccLink.href });
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

  const loginCallout = document.getElementById('aboutLoginCallout');
  if (loginCallout) {
    loginCallout.style.display = userEmail ? 'none' : 'flex';
  }

  if (modalStartBtn) {
    modalStartBtn.focus();
  }
  trackEvent('about_modal_opened');
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
  trackEvent('about_modal_closed');
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

const aboutLoginBtn = document.getElementById('aboutLoginBtn');
if (aboutLoginBtn) {
  aboutLoginBtn.addEventListener('click', () => {
    closeModal();
    setTimeout(openPrefModal, 300);
  });
}

// Preferences Modal Elements
const prefModal = document.getElementById('prefModal');
const prefBtn = document.getElementById('prefBtn');
const prefBtnText = document.getElementById('prefBtnText');
const prefCloseBtn = document.getElementById('prefCloseBtn');
const prefLoggedOutState = document.getElementById('prefLoggedOutState');
const prefLoggedInState = document.getElementById('prefLoggedInState');

const loginEmailInput = document.getElementById('loginEmailInput');
const loginErrorMsg = document.getElementById('loginErrorMsg');
const loginSubmitBtn = document.getElementById('loginSubmitBtn');

const loggedInEmailText = document.getElementById('loggedInEmailText');
const signOutBtn = document.getElementById('signOutBtn');
const savePrefBtn = document.getElementById('savePrefBtn');

// userEmail, currentPrefs, lifestylePrefs declared in state.js
// switchView, enterChatMode, exitChatMode declared in ui.js

// Step-by-Step wizard controller
const tabCoreBtn = document.getElementById('tabCoreBtn');
const tabHomeBtn = document.getElementById('tabHomeBtn');
const tabLifeBtn = document.getElementById('tabLifeBtn');
const stepCore = document.getElementById('stepCore');
const stepHome = document.getElementById('stepHome');
const stepLife = document.getElementById('stepLife');
const prefBackBtn = document.getElementById('prefBackBtn');
let activeWizardStep = 1;

function showWizardStep(stepNum) {
  activeWizardStep = stepNum;
  const tabs = [tabCoreBtn, tabHomeBtn, tabLifeBtn];
  const steps = [stepCore, stepHome, stepLife];

  tabs.forEach((tab, idx) => {
    if (tab) {
      if (idx + 1 === stepNum) {
        tab.classList.add('active');
        tab.style.background = 'var(--accent)';
        tab.style.color = 'var(--accent-text)';
      } else {
        tab.classList.remove('active');
        tab.style.background = 'transparent';
        tab.style.color = 'var(--text-muted)';
      }
    }
  });

  steps.forEach((step, idx) => {
    if (step) {
      if (idx + 1 === stepNum) {
        step.style.display = 'flex';
        step.classList.add('active');
      } else {
        step.style.display = 'none';
        step.classList.remove('active');
      }
    }
  });

  // Dynamic Puppy Stepper animation
  const progressBar = document.getElementById('quizProgressBar');
  const progressPuppy = document.getElementById('quizProgressPuppy');
  if (progressBar && progressPuppy) {
    let pct = 33;
    if (stepNum === 2) pct = 66;
    else if (stepNum === 3) pct = 100;
    progressBar.style.width = pct + '%';
    progressPuppy.style.left = `calc(${pct}% - 13px)`;
  }

  if (stepNum === 1) {
    if (prefBackBtn) prefBackBtn.style.display = 'none';
    if (savePrefBtn) savePrefBtn.innerHTML = 'Continue ➔';
  } else if (stepNum === 2) {
    if (prefBackBtn) prefBackBtn.style.display = 'flex';
    if (savePrefBtn) savePrefBtn.innerHTML = 'Continue ➔';
  } else {
    if (prefBackBtn) prefBackBtn.style.display = 'flex';
    if (savePrefBtn) savePrefBtn.innerHTML = 'Save Selections ✨';
  }
}

if (tabCoreBtn) tabCoreBtn.addEventListener('click', () => showWizardStep(1));
if (tabHomeBtn) tabHomeBtn.addEventListener('click', () => showWizardStep(2));
if (tabLifeBtn) tabLifeBtn.addEventListener('click', () => showWizardStep(3));
if (prefBackBtn) {
  prefBackBtn.addEventListener('click', () => {
    if (activeWizardStep === 2) showWizardStep(1);
    else if (activeWizardStep === 3) showWizardStep(2);
  });
}

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
    prefBtnText.textContent = userEmail ? 'Fit' : 'Fit';
  }
}

function openPrefModal() {
  if (!prefModal) return;
  prefModal.classList.add('active');
  prefModal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';

  showWizardStep(1); // Default to Step 1 basics on open

  if (userEmail) {
    prefLoggedOutState.style.display = 'none';
    prefLoggedInState.style.display = 'block';
    if (loggedInEmailText) loggedInEmailText.textContent = userEmail.split('@')[0] + "'s Profile";

    // Setup initial button states from current preferences
    setupSelectorButtons('prefGenderGroup', currentPrefs.gender);
    setupSelectorButtons('prefAgeGroup', currentPrefs.age_group);
    setupSelectorButtons('prefSizeGroup', currentPrefs.size);
    setupSelectorButtons('prefLocationGroup', currentPrefs.location || 'any');
    setupSelectorButtons('prefEnergyGroup', lifestylePrefs.energy || 'any');
    setupSelectorButtons('prefHomeGroup', lifestylePrefs.home || 'any');

    // Setup toggle badge states
    setupToggleBadge('prefOptKids', lifestylePrefs.kids);
    setupToggleBadge('prefOptDogs', lifestylePrefs.dogs);
    setupToggleBadge('prefOptCats', lifestylePrefs.cats);
    setupToggleBadge('prefOptShed', lifestylePrefs.shedding);
    setupToggleBadge('prefOptAlone', lifestylePrefs.aloneTime);
    setupToggleBadge('prefOptLearn', lifestylePrefs.training);
  } else {
    prefLoggedOutState.style.display = 'block';
    prefLoggedInState.style.display = 'none';
    if (loginEmailInput) {
      loginEmailInput.value = '';
      loginEmailInput.focus();
    }
    if (loginErrorMsg) loginErrorMsg.style.display = 'none';
  }
  trackEvent('preferences_modal_opened');
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
  trackEvent('preferences_modal_closed');
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
const prefHomeGroup = document.getElementById('prefHomeGroup');

if (prefGenderGroup) prefGenderGroup.addEventListener('click', handleSelectorClick);
if (prefAgeGroup) prefAgeGroup.addEventListener('click', handleSelectorClick);
if (prefSizeGroup) prefSizeGroup.addEventListener('click', handleSelectorClick);
if (prefLocationGroup) prefLocationGroup.addEventListener('click', handleSelectorClick);
if (prefEnergyGroup) prefEnergyGroup.addEventListener('click', handleSelectorClick);
if (prefHomeGroup) prefHomeGroup.addEventListener('click', handleSelectorClick);

// Bind custom toggle badges inside Lifestyle Step 2
const lifestyleButtons = [
  { id: 'prefOptKids', key: 'kids' },
  { id: 'prefOptDogs', key: 'dogs' },
  { id: 'prefOptCats', key: 'cats' },
  { id: 'prefOptShed', key: 'shedding' },
  { id: 'prefOptAlone', key: 'aloneTime' },
  { id: 'prefOptLearn', key: 'training' }
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

// frictionless sign in API
async function handleLogin() {
  const email = loginEmailInput.value.trim();
  if (!email || !email.includes('@')) {
    loginErrorMsg.textContent = 'Please enter a valid email address.';
    loginErrorMsg.style.display = 'block';
    return;
  }

  loginSubmitBtn.disabled = true;
  loginSubmitBtn.textContent = 'Signing in...';

  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });

    if (!response.ok) throw new Error('Authentication failed');

    const profile = await response.json();

    userEmail = profile.email;
    localStorage.setItem('chattyhound_user_email', userEmail);
    trackEvent('user_signed_in');
    updateProfileButton();

    const hasCustomPrefs = Object.values(currentPrefs).some(v => v && v !== 'any') || Object.values(lifestylePrefs).some(v => v !== 'any' && v !== false);
    const isFromNextDog = window.__CH_INTERRUPTED_NEXT_DOG__ || document.getElementById('landingView').classList.contains('active');

    if (hasCustomPrefs) {
      // Auto-save guest preferences to backend
      await fetch('/api/save_preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: userEmail, ...currentPrefs })
      });
    } else {
      // Load backend preferences
      currentPrefs = {
        gender: profile.gender || 'any',
        age_group: profile.age_group || 'any',
        size: profile.size || 'any',
        location: profile.location || 'any'
      };
    }

    syncLocalFavoritesToBackend(userEmail);
    const savedNavBtnEl = document.getElementById('savedNavBtn');
    if (savedNavBtnEl) savedNavBtnEl.style.display = '';
    updateSavedNavBadge();

    const hasBackendPrefs = profile.gender && profile.gender !== 'any' || profile.age_group && profile.age_group !== 'any' || profile.size && profile.size !== 'any' || profile.location && profile.location !== 'any';
    const hasDefinedPrefs = hasCustomPrefs || hasBackendPrefs;

    // Unconditionally skip the wizard and route to a dog upon successful sign-in
    closePrefModal();
    switchView('app');
    if (window.__CH_INTERRUPTED_NEXT_DOG__) {
      window.__CH_INTERRUPTED_NEXT_DOG__ = false;
    }
    fetchRandomDog();

  } catch (err) {
    console.error(err);
    loginErrorMsg.textContent = 'Trouble signing in. Please check connection and try again.';
    loginErrorMsg.style.display = 'block';
  } finally {
    loginSubmitBtn.disabled = false;
    loginSubmitBtn.textContent = 'Continue';
  }
}

// Save preferences API
async function handleSavePreferences() {
  // If we are on Step 1, transition to Step 2
  if (activeWizardStep === 1) {
    showWizardStep(2);
    return;
  }

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
  const homeActive = document.getElementById('prefHomeGroup').querySelector('.pref-btn.active');
  lifestylePrefs.energy = energyActive ? energyActive.getAttribute('data-value') : 'any';
  lifestylePrefs.home = homeActive ? homeActive.getAttribute('data-value') : 'any';
  localStorage.setItem('chattyhound_lifestyle_prefs', JSON.stringify(lifestylePrefs));

  savePrefBtn.disabled = true;
  savePrefBtn.textContent = 'Saving...';

  // If user is not logged in / email-less, save locally and transition directly!
  if (!userEmail) {
    currentPrefs = { gender, age_group, size, location };
    closePrefModal();
    trackEvent('preferences_saved', { gender, age_group, size, location, ...lifestylePrefs });
    switchView('app'); // Transition to active dog matching cards!
    fetchRandomDog();
    savePrefBtn.disabled = false;
    savePrefBtn.innerHTML = 'Save Selections ✨';
    return;
  }

  try {
    const response = await fetch('/api/save_preferences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: userEmail, gender, age_group, size, location })
    });

    if (!response.ok) throw new Error('Failed to save preferences');

    const data = await response.json();
    currentPrefs = {
      gender: data.preferences.gender,
      age_group: data.preferences.age_group,
      size: data.preferences.size,
      location: data.preferences.location || 'any'
    };

    closePrefModal();
    trackEvent('preferences_saved', { gender, age_group, size, location, ...lifestylePrefs });
    switchView('app'); // Transition to active dog matching cards!
    // Fetch new random dog matching these preferences
    fetchRandomDog();

  } catch (err) {
    console.error(err);
    alert('Trouble saving preferences. Please try again.');
  } finally {
    savePrefBtn.disabled = false;
    savePrefBtn.innerHTML = 'Save Selections ✨';
  }
}

async function resetPreferences() {
  // 1. Clear local state
  currentPrefs = { gender: 'any', age_group: 'any', size: 'any', location: 'any' };
  lifestylePrefs = {
    energy: 'any',
    home: 'any',
    kids: false,
    dogs: false,
    cats: false,
    shedding: false,
    aloneTime: false,
    training: false
  };

  // 2. Write to localStorage
  localStorage.setItem('chattyhound_lifestyle_prefs', JSON.stringify(lifestylePrefs));

  // 3. Update the selectors visually so that if user opens preferences again, it is correctly reset
  setupSelectorButtons('prefGenderGroup', 'any');
  setupSelectorButtons('prefAgeGroup', 'any');
  setupSelectorButtons('prefSizeGroup', 'any');
  setupSelectorButtons('prefLocationGroup', 'any');
  setupSelectorButtons('prefEnergyGroup', 'any');
  setupSelectorButtons('prefHomeGroup', 'any');
  lifestyleButtons.forEach(item => setupToggleBadge(item.id, false));

  // 4. Save to backend if user is logged in
  if (userEmail) {
    try {
      await fetch('/api/save_preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: userEmail, gender: 'any', age_group: 'any', size: 'any', location: 'any' })
      });
    } catch (err) {
      console.error("Failed to reset backend preferences:", err);
    }
  }

  trackEvent('preferences_reset_all');

  // 5. Trigger a fresh match load
  await fetchRandomDog();
}

function handleSignOut() {
  userEmail = null;
  currentPrefs = { gender: 'any', age_group: 'any', size: 'any', location: 'any' };
  lifestylePrefs = {
    energy: 'any',
    home: 'any',
    kids: false,
    dogs: false,
    cats: false,
    shedding: false,
    aloneTime: false,
    training: false
  };
  localStorage.removeItem('chattyhound_user_email');
  localStorage.removeItem('chattyhound_lifestyle_prefs');

  // Update badge selectors visual classes
  lifestyleButtons.forEach(item => setupToggleBadge(item.id, false));

  updateProfileButton();
  closePrefModal();
  // Remove match badge
  const badgeContainer = document.getElementById('prefMatchBadgeContainer');
  if (badgeContainer) badgeContainer.innerHTML = '';
  trackEvent('user_signed_out');
  // Transition back to Landing page mode on Sign Out!
  switchView('landing');
  fetchRandomDog();
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

if (loginSubmitBtn) loginSubmitBtn.addEventListener('click', handleLogin);
if (loginEmailInput) {
  loginEmailInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleLogin();
  });
}
if (savePrefBtn) {
  savePrefBtn.addEventListener('click', () => {
    if (activeWizardStep === 1) showWizardStep(2);
    else if (activeWizardStep === 2) showWizardStep(3);
    else handleSavePreferences();
  });
}
if (signOutBtn) signOutBtn.addEventListener('click', handleSignOut);
// Collapsible biography click trigger
const aboutDogToggle = document.getElementById('aboutDogToggle');
const aboutDogText = document.getElementById('aboutDogText');
if (aboutDogToggle && aboutDogText) {
  aboutDogToggle.addEventListener('click', () => {
    const fullBio = aboutDogText.dataset.fullBio || '';
    const isCollapsed = aboutDogText.classList.toggle('collapsed');
    if (isCollapsed) {
      aboutDogText.textContent = fullBio.slice(0, 180) + '...';
      aboutDogToggle.innerHTML = `See more <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 2px;"><polyline points="6 9 12 15 18 9"/></svg>`;
      trackEvent('bio_collapsed', { dog_name: currentDogName });
    } else {
      aboutDogText.textContent = fullBio;
      aboutDogToggle.innerHTML = `See less <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 2px;"><polyline points="18 15 12 9 6 15"/></svg>`;
      trackEvent('bio_expanded', { dog_name: currentDogName });
    }
  });
}
