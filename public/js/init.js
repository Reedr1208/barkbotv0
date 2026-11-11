// ─── App Initialization ─────────────────────────────────────────────────────
// Startup, route handling, event listener wiring, and locations population

// ─── Locations + Shelters Data Population ───────────────────────────────
// Feeds the shared Location/Shelter filter (filters.js). Initial scope comes from the
// URL when present (/nyc, /nyc/bideawee, /dogs/nyc/..., /dogs/alldogs/...), else stored prefs.
window.__CH_LOCATIONS_PROMISE__ = (async function populateLocations() {
  try {
    const locUrl = userEmail ? '/api/locations?email=' + encodeURIComponent(userEmail) : '/api/locations';
    const res = await fetch(locUrl);
    if (res.ok) {
      const data = await res.json();
      if (data.locations) {
        window.__CH_LOCATIONS_DATA__ = data.locations;
        window.__CH_SHELTERS_DATA__ = data.shelters || [];
        initFilterState();
      }
    }
  } catch (e) {
    console.error("Error fetching locations:", e);
  }
})();

// ─── Location Personalization for Landing Page ───────────────────────────
function personalizeForLocation(displayName) {
  if (!displayName) return;
  // Extract short city name (e.g. "Tucson" from "Tucson, AZ 🌵")
  const cityShort = displayName.replace(/,.*$/, '').trim();
  if (!cityShort) return;

  // Update the location chip
  const chip = document.getElementById('landingLocationChip');
  const chipText = document.getElementById('landingLocationChipText');
  if (chip && chipText) {
    chipText.textContent = cityShort + '-area dogs ready';
    chip.classList.add('visible');
  }

  // Update the title
  const titleEl = document.getElementById('landingTitle');
  if (titleEl) {
    titleEl.innerHTML = cityShort + ' dogs <span class="gradient-text-accent">are online.</span><br>Go ask them something weird.';
  }

  // Update the subtitle
  const subEl = document.getElementById('landingSub');
  if (subEl) {
    subEl.textContent = 'Meet adoptable shelter dogs around ' + cityShort + ' through playful AI conversations that reveal the energy, quirks, and home life hiding behind the kennel card.';
  }

  // Update the CTA button
  const startBtn = document.getElementById('landingStartBtn');
  if (startBtn) {
    startBtn.innerHTML = 'Chat with ' + cityShort + ' hounds <span aria-hidden="true">→</span>';
  }

  // Update the dog card location label
  const cardLabel = document.getElementById('landingCardLocationLabel');
  if (cardLabel) cardLabel.textContent = cityShort;

  // Update how-it-works section
  const howTitle = document.getElementById('landingHowTitle');
  if (howTitle) howTitle.textContent = 'A better first hello for ' + cityShort + '.';

  const step1 = document.getElementById('landingStep1');
  if (step1) step1.textContent = 'Browse dogs available near ' + cityShort + '.';

  // Store the detected city for later use in Start Sniffing handler
  window.__CH_DETECTED_CITY__ = displayName;
}

// If city was injected server-side (e.g. /tucson route), personalize immediately
if (window.__CH_DETECTED_CITY__) {
  personalizeForLocation(window.__CH_DETECTED_CITY__);
  trackEvent('location_detected', { location: window.__CH_DETECTED_CITY__, method: 'route' });
} else {
  // Race geo detection vs a short timeout.
  // Content stays hidden until one wins, then renders exactly once — no flash.
  const _landingCopy = document.querySelector('.landing-copy');
  if (_landingCopy) {
    _landingCopy.style.opacity = '0';
    _landingCopy.style.transition = 'opacity 0.4s ease';
  }

  const _geoDetect = fetch('/api/detect_location')
    .then(r => r.ok ? r.json() : null)
    .then(d => d?.location || null)
    .catch(() => null);

  const _deadline = new Promise(resolve => setTimeout(() => resolve(null), 1200));

  Promise.race([_geoDetect, _deadline]).then(location => {
    if (location) {
      personalizeForLocation(location);
      trackEvent('location_detected', { location, method: 'geo_ip' });
    } else {
      trackEvent('location_detected', { location: 'none', method: 'timeout_or_failed' });
    }
    if (_landingCopy) _landingCopy.style.opacity = '1';
  });
}

// ─── Landing Page & Navigation Wiring ────────────────────────────────────
const landingStartBtn = document.getElementById('landingStartBtn');
if (landingStartBtn) {
  landingStartBtn.addEventListener('click', async () => {
    trackEvent('start_sniffing_clicked');
    switchView('app');

    // Use the detected city if available, otherwise try to detect
    const detectedCity = window.__CH_DETECTED_CITY__;
    if (detectedCity && (!currentPrefs.location || currentPrefs.location === 'any' || currentPrefs.location === 'all')) {
      await window.__CH_LOCATIONS_PROMISE__;  // ensure locations data is loaded
      setFilterState({ location: detectedCity, shelter: null }, { source: 'detect', track: false });
    } else if (!currentPrefs.location || currentPrefs.location === 'any' || currentPrefs.location === 'all') {
      // Fallback: try API detection
      try {
        await window.__CH_LOCATIONS_PROMISE__;
        const detectRes = await fetch('/api/detect_location');
        if (detectRes.ok) {
          const detectData = await detectRes.json();
          if (detectData.location) {
            setFilterState({ location: detectData.location, shelter: null }, { source: 'detect', track: false });
          }
        }
      } catch (e) {
        console.warn('Location auto-detect failed:', e);
      }
    }

    await fetchSuggestedPromptsIfNeeded();
    fetchRandomDog();
  });
}

const landingLoginBtn = document.getElementById('landingLoginBtn');
if (landingLoginBtn) {
  landingLoginBtn.addEventListener('click', () => {
    openPrefModal();
  });
}

const landingPrefBtn = document.getElementById('landingPrefBtn');
if (landingPrefBtn) {
  landingPrefBtn.addEventListener('click', () => {
    openPrefModal();
  });
}


// Cleaned up: loginSkipBtn and loginGuestBtn removed (no longer exist in HTML)


// Sticky mobile action bar overlays
const mobileShuffleBtn = document.getElementById('mobileShuffleBtn');
const mobileChatBtn = document.getElementById('mobileChatBtn');

if (mobileShuffleBtn) {
  mobileShuffleBtn.addEventListener('click', () => {
    _trackDogExit();
    fetchRandomDog();
  });
}

if (mobileChatBtn) {
  mobileChatBtn.addEventListener('click', () => {
    const chatSec = document.getElementById('chatSection');
    if (chatSec && scrollContent) {
      chatSec.scrollIntoView({ behavior: 'smooth' });
      setTimeout(() => {
        if (chatInput) chatInput.focus();
      }, 400);
    }
  });
}

const dogUnavailableCtaBtn = document.getElementById('dogUnavailableCtaBtn');
if (dogUnavailableCtaBtn) {
  dogUnavailableCtaBtn.addEventListener('click', () => {
    setAppState('loading');
    history.replaceState({}, '', '/');
    fetchRandomDog();
  });
}




window.addEventListener('popstate', () => {
  // Restore the Location/Shelter scope encoded in the path (no history push, no refetch here)
  if (typeof applyFilterFromPath === 'function') applyFilterFromPath(window.location.pathname);
  if (typeof closeFilterPanel === 'function') closeFilterPanel({ returnFocus: false });

  if (typeof isBrowseMode !== 'undefined' && isBrowseMode) {
    openBrowseView();
    return;
  }
  const routeDogId = getDogIdFromPath();
  if (routeDogId) {
    openSharedDogFromRoute(routeDogId);
  } else if (localStorage.getItem('chattyhound_visited') === 'true') {
    fetchRandomDog();
  }
});

async function startAppAfterPreferences(loaderFn) {
  if (window.__CH_LOCATIONS_PROMISE__) {
    await window.__CH_LOCATIONS_PROMISE__;
  }

  // Pre-fetch suggested prompts pool (Informative/Whimsical) before first dog loads
  await fetchSuggestedPromptsIfNeeded();

  // Guest-only: just run the loader directly
  updateProfileButton();
  loaderFn();
}

// Initial Login Setup check, shared dog routes, and auto-fetch
const hasVisited = localStorage.getItem('chattyhound_visited');
const routeDogId = window.__CH_INITIAL_DOG_ID__ || getDogIdFromPath();

if (routeDogId) {
  startAppAfterPreferences(() => openSharedDogFromRoute(routeDogId));
} else if (hasVisited === 'true' || window.__CH_INITIAL_LOCATION__) {
  switchView('app');
  localStorage.setItem('chattyhound_visited', 'true');
  startAppAfterPreferences(() => fetchRandomDog());
} else {
  switchView('landing');
  updateProfileButton();
}

// Sticky Dog Bar — show when hero scrolls out of view
const stickyDogBar = document.getElementById('stickyDogBar');
const heroSection = document.querySelector('.hero-section');

if (stickyDogBar && heroSection && scrollContent) {
  const heroObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) {
          stickyDogBar.classList.add('visible');
        } else {
          stickyDogBar.classList.remove('visible');
        }
      });
    },
    {
      root: scrollContent,
      threshold: 0
    }
  );
  heroObserver.observe(heroSection);
}



// ─── Viewport, Keyboard & Accessibility ──────────────────────────────────
// Keep floating elements perfectly aligned with keyboard on mobile viewports
if (window.visualViewport) {
  const appContainer = document.querySelector('.app-container');
  const updateKeyboardOffset = () => {
    if (window.innerWidth <= 480 && appContainer) {
      // Size the app container exactly to the visual viewport height!
      // This natively shrinks the app to fit the space above the keyboard.
      appContainer.style.height = `${window.visualViewport.height}px`;
      appContainer.style.top = `${window.visualViewport.offsetTop}px`;
      
      // Set keyboard offset to 0 because the container itself has shrunk!
      document.documentElement.style.setProperty('--keyboard-offset', '0px');
      
      // If the chat input is focused, scroll the content to the bottom so they can see the chat box!
      if (document.activeElement === chatInput) {
        scrollToBottom();
      }
    } else {
      // Reset styles on desktop
      if (appContainer) {
        appContainer.style.height = '';
        appContainer.style.top = '';
      }
      const offset = window.innerHeight - window.visualViewport.height;
      const keyboardOffset = Math.max(0, offset);
      document.documentElement.style.setProperty('--keyboard-offset', `${keyboardOffset}px`);
    }
  };
  window.visualViewport.addEventListener('resize', updateKeyboardOffset);
  window.visualViewport.addEventListener('scroll', updateKeyboardOffset);
  updateKeyboardOffset();
}

// Force viewport scale snap reset on orientation change to fix iOS zoom bugs
window.addEventListener('orientationchange', () => {
  const viewport = document.querySelector('meta[name="viewport"]');
  if (viewport) {
    viewport.setAttribute('content', 'width=device-width, initial-scale=1.0, maximum-scale=1.0');
    setTimeout(() => {
      viewport.setAttribute('content', 'width=device-width, initial-scale=1.0');
      window.scrollTo(0, 0);
    }, 300);
  }
});

// Completely block native window layout scroll to prevent iOS Safari input focus layout offset bugs
// Only when the app view is active (landing page and browse view need native scrolling)
window.addEventListener('scroll', () => {
  const landingView = document.getElementById('landingView');
  const browseView = document.getElementById('browseView');
  const isLanding = landingView && !landingView.classList.contains('hidden');
  const isBrowse = browseView && !browseView.classList.contains('hidden');
  if (!isLanding && !isBrowse && (window.scrollY !== 0 || window.scrollX !== 0)) {
    window.scrollTo(0, 0);
  }
}, { passive: true });

// Completely block scrollContent from scrolling on desktop viewports
// scrollContent belongs to the app view, not the landing view
if (scrollContent) {
  scrollContent.addEventListener('scroll', () => {
    if (window.innerWidth >= 800 && scrollContent.scrollTop !== 0) {
      scrollContent.scrollTop = 0;
    }
  }, { passive: true });
}

// A11y: Trap focus inside active modal overlay cards on desktop viewports
function setupFocusTrap(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const focusables = Array.from(modal.querySelectorAll('button, [href], input, select, textarea, [tabindex="0"]'))
      .filter(el => {
        // Ensure elements are focusable and visible
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && el.getAttribute('disabled') === null;
      });
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first) {
        last.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    }
  });
}
setupFocusTrap('aboutModal');
setupFocusTrap('prefModal');
setupFocusTrap('savedModal');
// Swipe Navigation Logic
let touchStartX = 0;
let touchStartY = 0;
let touchEndX = 0;
let touchEndY = 0;

document.addEventListener('touchstart', e => {
  touchStartX = e.changedTouches[0].screenX;
  touchStartY = e.changedTouches[0].screenY;
}, {passive: true});

document.addEventListener('touchend', e => {
  touchEndX = e.changedTouches[0].screenX;
  touchEndY = e.changedTouches[0].screenY;
  handleSwipe();
}, {passive: true});

function handleSwipe() {
  const dx = touchEndX - touchStartX;
  const dy = touchEndY - touchStartY;
  
  // Ensure swipe is mostly horizontal and meets minimum distance
  if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 60) {
    if (dx < 0) {
      // Swiped right-to-left
      if (!document.body.classList.contains('chat-engaged')) {
        // Not in chat mode -> Next dog
        const nextBtn = document.getElementById('nextBtn');
        if (nextBtn && !nextBtn.disabled) {
          fetchRandomDog();
        }
      }
    } else {
      // Swiped left-to-right
      if (document.body.classList.contains('chat-engaged')) {
        // In chat mode -> Exit chat mode (highest priority)
        exitChatMode();
      } else if (previousDogId) {
        // On profile page -> Go back to previous dog
        goToPreviousDog();
      }
    }
  }
}

