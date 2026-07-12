// ─── App Initialization ─────────────────────────────────────────────────────
// Startup, route handling, event listener wiring, and locations population

// ─── Locations Data Population ───────────────────────────────────────────
window.__CH_LOCATIONS_PROMISE__ = (async function populateLocations() {
  try {
    const locUrl = userEmail ? '/api/locations?email=' + encodeURIComponent(userEmail) : '/api/locations';
    const res = await fetch(locUrl);
    if (res.ok) {
      const data = await res.json();
      const group = document.getElementById('prefLocationGroup');
      const headerSelect = document.getElementById('headerLocationSelect');
      if (data.locations) {
        window.__CH_LOCATIONS_DATA__ = data.locations;
        
        if (group) {
          group.innerHTML = '<button class="pref-btn" data-value="all">All Locations 🌎</button>';
          data.locations.forEach(loc => {
            const btn = document.createElement('button');
            btn.className = 'pref-btn';
            btn.dataset.value = loc.display_name;
            btn.textContent = loc.display_name;
            group.appendChild(btn);
          });
        }
        
        if (headerSelect) {
          headerSelect.innerHTML = '<option value="any" style="display:none;">Select Location...</option><option value="all" style="color: black;">All Locations 🌎</option>';
          data.locations.forEach(loc => {
            const opt = document.createElement('option');
            opt.value = loc.relative_path;
            opt.style.color = 'black';
            opt.textContent = loc.display_name;
            headerSelect.appendChild(opt);
          });
        }

        // Determine initial location from injected meta or preferences
        const initLoc = window.__CH_INITIAL_LOCATION__ || null;
        if (initLoc && headerSelect) {
          if (initLoc === '/alldogs') {
            headerSelect.value = 'all';
            setupSelectorButtons('prefLocationGroup', 'all');
            currentPrefs.location = 'all';
          } else {
            headerSelect.value = initLoc;
            // Also update preferences modal silently
            const locObj = data.locations.find(l => l.relative_path === initLoc);
            if (locObj) {
              setupSelectorButtons('prefLocationGroup', locObj.display_name);
              currentPrefs.location = locObj.display_name;
            }
          }
        } else if (currentPrefs && currentPrefs.location) {
          setupSelectorButtons('prefLocationGroup', currentPrefs.location);
          if (currentPrefs.location === 'all' && headerSelect) {
            headerSelect.value = 'all';
          } else {
            const locObj = data.locations.find(l => l.display_name === currentPrefs.location);
            if (locObj && headerSelect) headerSelect.value = locObj.relative_path;
          }
        }

        // Bind event listener to headerLocationSelect
        if (headerSelect) {
          headerSelect.addEventListener('change', async (e) => {
            const selectedPath = e.target.value;
            const locObj = data.locations.find(l => l.relative_path === selectedPath);
            
            // Update preferences
            const newLocName = locObj ? locObj.display_name : (selectedPath === 'all' ? 'all' : 'any');
            currentPrefs.location = newLocName;
            setupSelectorButtons('prefLocationGroup', newLocName);
            if (userEmail) {
              try {
                await fetch('/api/save_preferences', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ email: userEmail, preferences: currentPrefs })
                });
              } catch (e) {
                console.error('Failed to save location preference', e);
              }
            }
            
            // Check if current dog matches new location
            let shouldKeepDog = false;
            if ((selectedPath === 'all' || selectedPath === 'any') && currentDogData) {
              shouldKeepDog = true;
            } else if (locObj && currentDogData && currentDogData.shelter_id) {
              if (locObj.shelter_ids.includes(currentDogData.shelter_id)) {
                shouldKeepDog = true;
              }
            }
            
            if (shouldKeepDog) {
              // Just update URL and stay
              let targetUrl = `/dogs/${currentDogData.animal_id}`;
              if (selectedPath === 'all') targetUrl = `/dogs/alldogs/${currentDogData.animal_id}`;
              else if (selectedPath !== 'any') targetUrl = `/dogs${selectedPath}/${currentDogData.animal_id}`;
              window.location.href = targetUrl;
            } else {
              // Redirect to the new location path (will trigger a new random fetch)
              let targetUrl = '/dogs';
              if (selectedPath === 'all') targetUrl = '/dogs/alldogs';
              else if (selectedPath !== 'any') targetUrl = `/dogs${selectedPath}`;
              window.location.href = targetUrl;
            }
          });
        }
      }
    }
  } catch (e) {
    console.error("Error fetching locations:", e);
  }
})();

// ─── Landing Page & Navigation Wiring ────────────────────────────────────
// Landing and Empty state triggers
const landingStartBtn = document.getElementById('landingStartBtn');
const landingHowBtn = document.getElementById('landingHowBtn');
const loginSkipBtn = document.getElementById('loginSkipBtn');

if (landingStartBtn) {
  landingStartBtn.addEventListener('click', async () => {
    trackEvent('start_sniffing_clicked');
    switchView('app');
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

// Cleaned up landingHowBtn

if (loginSkipBtn) {
  loginSkipBtn.addEventListener('click', () => {
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

const loginGuestBtn = document.getElementById('loginGuestBtn');
if (loginGuestBtn) {
  loginGuestBtn.addEventListener('click', () => {
    document.getElementById('prefLoggedOutState').style.display = 'none';
    document.getElementById('prefLoggedInState').style.display = 'block';
    if (loggedInEmailText) loggedInEmailText.textContent = "Guest Profile";
  });
}

// Sticky mobile action bar overlays
const mobileShuffleBtn = document.getElementById('mobileShuffleBtn');
const mobileChatBtn = document.getElementById('mobileChatBtn');

if (mobileShuffleBtn) {
  mobileShuffleBtn.addEventListener('click', () => {
    trackEvent('dog_shuffled');
    fetchRandomDog();
  });
}

if (mobileChatBtn) {
  mobileChatBtn.addEventListener('click', () => {
    trackEvent('sticky_chat_clicked', { dog_name: currentDogName, animal_id: currentAnimalId });
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

// Report an issue button wiring
const reportIssueBtn = document.getElementById('reportIssueBtn');
if (reportIssueBtn) {
  reportIssueBtn.addEventListener('click', () => {
    trackEvent('issue_reported', { dog_name: currentDogName, animal_id: currentAnimalId });
    showToast("Thank you! Report received and sent to shelter team. 🐾");
    reportIssueBtn.textContent = "Reported ✓";
    reportIssueBtn.disabled = true;
    reportIssueBtn.style.color = "var(--text-muted)";
    reportIssueBtn.style.textDecoration = "none";
    reportIssueBtn.style.cursor = "default";
  });
}

window.addEventListener('popstate', () => {
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
  
  if (userEmail) {
    (async function fetchPreferencesOnLoad() {
      try {
        const response = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: userEmail })
        });
        if (response.ok) {
          const profile = await response.json();
          const urlLocation = (window.__CH_INITIAL_LOCATION__ && currentPrefs.location !== 'any') ? currentPrefs.location : null;
          
          currentPrefs = {
            gender: profile.gender || 'any',
            age_group: profile.age_group || 'any',
            size: profile.size || 'any',
            location: urlLocation || profile.location || 'any'
          };

          // Sync header visual with loaded preference
          if (window.__CH_LOCATIONS_DATA__ && currentPrefs.location !== 'any') {
            const locObj = window.__CH_LOCATIONS_DATA__.find(l => l.display_name === currentPrefs.location);
            if (locObj && document.getElementById('headerLocationSelect')) {
              document.getElementById('headerLocationSelect').value = locObj.relative_path;
            }
          }
        }
      } catch (err) {
        console.error('Error restoring preferences:', err);
      }
      updateProfileButton();
      await loaderFn();
      syncLocalFavoritesToBackend(userEmail);
    })();
  } else {
    updateProfileButton();
    loaderFn();
  }
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
window.addEventListener('scroll', () => {
  if (window.scrollY !== 0 || window.scrollX !== 0) {
    window.scrollTo(0, 0);
  }
}, { passive: true });

// Completely block scrollContent from scrolling on desktop viewports
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
        // In chat mode -> Exit chat mode
        exitChatMode();
      }
    }
  }
}

