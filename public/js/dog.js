// ─── Dog Profile Loading ────────────────────────────────────────────────────
// fetchRandomDog, favorite handling, and marked configuration

// Configure marked options to be safe
marked.setOptions({
  breaks: true,
  gfm: true,
  headerIds: false
});

// ─── DOM Element References (module-level for shared use) ───────────────────
const profilePanel = document.getElementById('profilePanel');
const loader = document.getElementById('loader');
const dogImage = document.getElementById('dogImage');
const dogName = document.getElementById('dogName');
const dogId = document.getElementById('dogId');
const dogAge = document.getElementById('dogAge');
const dogWeight = document.getElementById('dogWeight');
const paccLink = document.getElementById('paccLink');
const nextBtn = document.getElementById('nextBtn');
const chatTitleName = document.getElementById('chatTitleName');
const chatHistory = document.getElementById('chatHistory');
const chatInput = document.getElementById('chatInput');
const chatInputWrapper = document.getElementById('chatInputWrapper');
const sendBtn = document.getElementById('sendBtn');
const favBtn = document.getElementById('favBtn');
const scrollContent = document.getElementById('scrollContent');

// Animate chat input for first-time visitors
if (chatInput && !localStorage.getItem('has_interacted_with_chat')) {
  chatInput.classList.add('attention-pulse');
  if (chatInputWrapper) chatInputWrapper.classList.add('attention-wrapper');
}

// ─── Favorite Heart Toggle ──────────────────────────────────────────────────
if (favBtn) {
  favBtn.addEventListener('click', async () => {
    if (!currentAnimalId) return;
    const index = favoritesList.indexOf(currentAnimalId);
    const removing = index > -1;

    // Optimistic UI update
    if (removing) {
      favoritesList.splice(index, 1);
      favBtn.classList.remove('favorited');
      favBtn.setAttribute('aria-label', `Save ${currentDogName} to My Dogs`);
      trackEvent('dog_unfavorited', { dog_name: currentDogName, animal_id: currentAnimalId });
      showToast(`Removed from My Dogs.`);
    } else {
      favoritesList.push(currentAnimalId);
      favBtn.classList.add('favorited');
      favBtn.setAttribute('aria-label', `Remove ${currentDogName} from My Dogs`);
      trackEvent('dog_favorited', { dog_name: currentDogName, animal_id: currentAnimalId });
      showToast(`Saved to My Dogs.`);
    }
    localStorage.setItem('chattyhound_favorites', JSON.stringify(favoritesList));
    updateSavedNavBadge();

    // Refresh the modal if open
    const modal = document.getElementById('savedModal');
    if (modal && modal.classList.contains('active') && savedActiveTab === 'dogs') {
      loadSavedTab('dogs');
    }

    // Backend sync if logged in
    if (userEmail) {
      try {
        const currentImageUrl = document.getElementById('dogImage')?.src || '';
        await fetch('/api/favorites', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: userEmail,
            animal_id: currentAnimalId,
            dog_name: currentDogName,
            dog_image_url: currentImageUrl,
            action: removing ? 'remove' : 'save'
          })
        });
      } catch (e) {
        console.warn('Favorites sync failed:', e);
      }
    }
  });
}

// ─── Back Navigation ────────────────────────────────────────────────────────

function goToPreviousDog() {
  if (!previousDogId) return;
  const idToLoad = previousDogId;
  previousDogId = null;
  updateBackBtnVisibility();
  fetchRandomDog(idToLoad);
}

function updateBackBtnVisibility() {
  const backBtn = document.getElementById('prevBtn');
  if (backBtn) {
    backBtn.style.display = previousDogId ? '' : 'none';
  }
}

// ─── Helper: Resolve dog image URL ──────────────────────────────────────────

function getDogImageUrl(dog) {
  if (dog.image_file && dog.image_base_url) return dog.image_base_url + dog.image_file;
  if (dog.shelter_image_url) return dog.shelter_image_url;
  return 'happy_rescue_pup.png';
}

// ─── resetProfileUI: Clear all DOM before loading a new dog ─────────────────

function resetProfileUI() {
  dogImage.src = '';
  dogName.textContent = '';
  dogId.textContent = '';
  dogAge.textContent = '';
  dogWeight.textContent = '';

  const locationTextEl = document.getElementById('dogLocationText');
  if (locationTextEl) locationTextEl.textContent = '';
  const dogBreedEl = document.getElementById('dogBreed');
  if (dogBreedEl) dogBreedEl.textContent = 'Rescue Mix 🐾';
  const lastCheckedEl = document.getElementById('lastCheckedDate');
  if (lastCheckedEl) lastCheckedEl.textContent = 'Today';

  // Reset rotate overlay
  const rotateDogPhoto = document.getElementById('rotateDogPhoto');
  const rotateDogTitle = document.getElementById('rotateDogTitle');
  const rotateDogText = document.getElementById('rotateDogText');
  if (rotateDogPhoto) rotateDogPhoto.src = 'happy_rescue_pup.png';
  if (rotateDogTitle) rotateDogTitle.innerHTML = 'Find your perfect match! 🐶';
  if (rotateDogText) rotateDogText.textContent = 'ChattyHound is optimized for portrait mode. Spin your device around to continue finding and chatting with shelter dogs! 🐾';

  // Hide personality section
  const secPersonality = document.getElementById('secPersonality');
  if (secPersonality) {
    secPersonality.style.display = 'none';
    secPersonality.setAttribute('aria-hidden', 'true');
  }

  paccLink.style.display = 'none';
  chatTitleName.textContent = '...';
  currentDogName = 'this dog';
  chatHistory.innerHTML = '';
  conversationHistory = [];
  chatInput.disabled = true;
  sendBtn.disabled = true;

  // Hide Why Fit card
  const whyFitCard = document.getElementById('whyFitCard');
  if (whyFitCard) whyFitCard.style.display = 'none';

  // Reset preference metadata (stat chip colors, compat dots)
  ['chipGender', 'chipAge', 'chipWeight'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.className = 'detail-chip';
  });
  ['dotGender', 'dotAge', 'dotWeight', 'dotLocation'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.display = 'none'; el.className = 'compat-dot'; }
  });
  ['noteGender', 'noteAge', 'noteWeight'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.display = 'none'; el.innerHTML = ''; }
  });
  const dogGender = document.getElementById('dogGender');
  if (dogGender) dogGender.textContent = '';

  // Reset report issue button
  const reportIssueBtn = document.getElementById('reportIssueBtn');
  if (reportIssueBtn) {
    reportIssueBtn.textContent = 'Report an issue';
    reportIssueBtn.disabled = false;
    reportIssueBtn.style.color = 'var(--accent)';
    reportIssueBtn.style.textDecoration = 'underline';
    reportIssueBtn.style.cursor = 'pointer';
  }

  profilePanel.classList.add('loading');
}

// ─── fetchDogData: Build URL, call API, return fetch Response ───────────────

async function fetchDogData(forcedAnimalId) {
  const params = [];
  if (forcedAnimalId) {
    params.push('animal_id=' + encodeURIComponent(forcedAnimalId));
  } else if (viewedIds.length > 0) {
    params.push('viewed=' + viewedIds.join(','));
  }
  if (currentPrefs.gender && currentPrefs.gender !== 'any') params.push('gender=' + encodeURIComponent(currentPrefs.gender));
  if (currentPrefs.age_group && currentPrefs.age_group !== 'any') params.push('age_group=' + encodeURIComponent(currentPrefs.age_group));
  if (currentPrefs.size && currentPrefs.size !== 'any') params.push('size=' + encodeURIComponent(currentPrefs.size));
  if (currentPrefs.location && currentPrefs.location !== 'any' && currentPrefs.location !== 'all') params.push('location=' + encodeURIComponent(currentPrefs.location));
  if (lifestylePrefs.energy && lifestylePrefs.energy !== 'any') params.push('energy=' + encodeURIComponent(lifestylePrefs.energy));
  if (lifestylePrefs.altered && lifestylePrefs.altered !== 'any') params.push('altered=' + encodeURIComponent(lifestylePrefs.altered));
  if (lifestylePrefs.dogs) params.push('dogs=true');
  if (lifestylePrefs.houseTrained) params.push('house_trained=true');

  return fetch('/api/random_dog?' + params.join('&'));
}

// ─── syncLocationDropdown: Update header location select to match loaded dog ─

function syncLocationDropdown(dog, forcedAnimalId) {
  const hs = document.getElementById('headerLocationSelect');
  if (!hs || !window.__CH_LOCATIONS_DATA__ || !dog.shelter_id) return;

  const dogLocObj = window.__CH_LOCATIONS_DATA__.find(l =>
    l.shelter_ids && l.shelter_ids.includes(dog.shelter_id)
  );

  // If user explicitly chose "All Locations", don't override dropdown to dog's specific location
  const userChoseAll = currentPrefs.location === 'all' || hs.value === 'all';

  if (forcedAnimalId && dogLocObj && !userChoseAll) {
    // Only sync to dog's location when user hasn't explicitly chosen "All Locations"
    hs.value = dogLocObj.relative_path;
    currentPrefs.location = dogLocObj.display_name;
    localStorage.setItem('chattyhound_prefs', JSON.stringify(currentPrefs));
    if (typeof setupSelectorButtons === 'function') {
      setupSelectorButtons('prefLocationGroup', dogLocObj.display_name);
    }
  } else if (!dog.user_has_preferences && hs.value === 'any') {
    hs.value = 'all';
  }
}

// ─── renderDogProfile: Populate all profile DOM elements ────────────────────

function renderDogProfile(dog) {
  const locationTextEl = document.getElementById('dogLocationText');

  currentDogName = dog.name || 'this dog';
  dogName.textContent = dog.name || 'Unknown';

  // Breed
  const dogBreedEl = document.getElementById('dogBreed');
  if (dogBreedEl) {
    let breedText = dog.breed_or_description || 'Rescue Mix';
    if (breedText.toLowerCase() === 'unknown') breedText = 'Unknown breed';
    dogBreedEl.textContent = breedText + ' 🐾';
  }

  chatTitleName.textContent = currentDogName;

  // Animal ID display (e.g. "A902682 • PACC")
  const idParts = dog.animal_id ? dog.animal_id.split('-') : [];
  const nativeId = idParts.length > 1 ? idParts.slice(1).join('-') : dog.animal_id;
  const shelterId = idParts.length > 0 ? idParts[0] : '';
  dogId.textContent = dog.animal_id ? `${nativeId} • ${shelterId}` : '';

  // Location & last checked
  if (locationTextEl) {
    locationTextEl.textContent = dog.shelter_name || 'Pima Animal Care Center';
  }
  const lastCheckedEl = document.getElementById('lastCheckedDate');
  if (lastCheckedEl) {
    lastCheckedEl.textContent = formatRelativeTime(dog.info_refreshed_at);
  }

  // Rotate overlay (landscape mode)
  const rotateDogPhoto = document.getElementById('rotateDogPhoto');
  const rotateDogTitle = document.getElementById('rotateDogTitle');
  const rotateDogText = document.getElementById('rotateDogText');
  if (rotateDogPhoto) rotateDogPhoto.src = getDogImageUrl(dog);
  if (rotateDogTitle) {
    rotateDogTitle.innerHTML = `Let's chat with <span style="color:var(--accent-hover);">${currentDogName}</span>! 🐾`;
  }
  if (rotateDogText) {
    rotateDogText.textContent = `To interact with ${currentDogName} or see more profile details, spin your device back to portrait mode!`;
  }

  // Buttons, labels, placeholders
  const askBtnTitle = document.getElementById('askBtnTitle');
  if (askBtnTitle) askBtnTitle.textContent = 'Ask ' + currentDogName;
  if (favBtn) {
    const isFav = favoritesList.includes(currentAnimalId);
    favBtn.setAttribute('aria-label', isFav ? `Remove ${currentDogName} from My Dogs` : `Save ${currentDogName} to My Dogs`);
  }
  if (paccLink) {
    paccLink.setAttribute('aria-label', `Open ${currentDogName}'s official shelter page on 24Petconnect`);
  }
  updateShareButtonLabels();
  if (chatInput) chatInput.placeholder = 'Ask about me!';

  // Sticky dog bar
  const stickyDogName = document.getElementById('stickyDogName');
  const stickyDogMeta = document.getElementById('stickyDogMeta');
  if (stickyDogName) stickyDogName.textContent = currentDogName;
  if (stickyDogMeta) {
    const agePart = cleanAgeText(dog.age || '');
    const weightPart = cleanWeightText(dog.weight || '');
    const parts = [agePart, weightPart].filter(p => p && p !== '-');
    stickyDogMeta.textContent = parts.join(' · ') || 'Shelter Dog';
  }

  // Stats panel (gender, age, weight)
  const genderEl = document.getElementById('dogGender');
  if (genderEl) genderEl.textContent = dog.sex || cleanGenderText(dog.gender || 'Unknown');
  dogAge.textContent = dog.age_summary || cleanAgeText(dog.age || 'Unknown');
  dogWeight.textContent = dog.weight_summary || cleanWeightText(dog.weight || 'Unknown');

  // Restore action overlays
  const mobileActionBar = document.getElementById('mobileActionBar');
  if (mobileActionBar) mobileActionBar.style.display = 'flex';
  const stickyDogBar = document.getElementById('stickyDogBar');
  if (stickyDogBar) stickyDogBar.style.display = 'flex';

  // Images (single helper resolves URL — no duplicate fallback branches)
  const imgUrl = getDogImageUrl(dog);
  dogImage.src = imgUrl;
  const stickyDogAvatar = document.getElementById('stickyDogAvatar');
  if (stickyDogAvatar) stickyDogAvatar.src = imgUrl;

  // Shelter links
  if (dog.shelter_profile_url) {
    paccLink.href = dog.shelter_profile_url;
    paccLink.style.display = 'inline-flex';
  }
  const mobileAdoptBtn = document.getElementById('mobileAdoptBtn');
  if (mobileAdoptBtn && dog.shelter_profile_url) mobileAdoptBtn.href = dog.shelter_profile_url;
  const stickyShelterBtn = document.getElementById('stickyShelterBtn');
  if (stickyShelterBtn && dog.shelter_profile_url) stickyShelterBtn.href = dog.shelter_profile_url;

  // Enable chat input
  chatInput.disabled = false;
  sendBtn.disabled = false;

  // Favorite heart state
  if (favBtn) {
    if (favoritesList.includes(currentAnimalId)) {
      favBtn.classList.add('favorited');
    } else {
      favBtn.classList.remove('favorited');
    }
  }
}

// ─── renderCompatBadges: Preference match dots + highlight badge ─────────────

function renderCompatBadges(dog) {
  const badgeContainer = document.getElementById('prefMatchBadgeContainer');
  if (badgeContainer) {
    badgeContainer.innerHTML = '';

    // Highlight badges — show all highlights from DB as green tags
    const highlights = dog.highlights || [];
    if (highlights.length > 0) {
      badgeContainer.innerHTML = highlights.map(h => {
        const escaped = document.createElement('span');
        escaped.textContent = h;
        return `<span class="fit-badge-tag">${escaped.innerHTML}</span>`;
      }).join('');
    } else {
      badgeContainer.innerHTML = '<span class="fit-badge-tag">Shelter Hero 🦸</span>';
    }
  }

  // Preference stat dots (green/yellow/gray) and Why Fit card
  if (dog.user_has_preferences && dog.match_details) {
    const hasConfiguredPrefs = Object.values(dog.match_details).some(cat => cat.active);

    if (hasConfiguredPrefs) {
      const categories = [
        { key: 'gender', boxId: 'chipGender', dotId: 'dotGender' },
        { key: 'age', boxId: 'chipAge', dotId: 'dotAge' },
        { key: 'size', boxId: 'chipWeight', dotId: 'dotWeight' },
        { key: 'location', boxId: 'dogLocation', dotId: 'dotLocation' }
      ];

      categories.forEach(cat => {
        const details = dog.match_details[cat.key];
        const box = document.getElementById(cat.boxId);
        const dot = document.getElementById(cat.dotId);
        if (!details || !box || !dot) return;

        dot.style.display = 'inline-block';
        if (details.active) {
          if (details.matched) {
            if (cat.boxId !== 'dogLocation') box.classList.add('matched');
            dot.className = 'compat-dot green';
          } else {
            if (cat.boxId !== 'dogLocation') box.classList.add('mismatched');
            dot.className = 'compat-dot yellow';
          }
        } else {
          dot.className = 'compat-dot gray';
        }
      });

      // Why Fit card summary
      const whyFitCard = document.getElementById('whyFitCard');
      const whyFitDesc = document.getElementById('whyFitDesc');
      if (whyFitCard && whyFitDesc) {
        whyFitCard.style.display = 'block';

        let matchCount = 0;
        let totalPrefs = 0;
        const matchesList = [];

        Object.keys(dog.match_details).forEach(key => {
          const details = dog.match_details[key];
          if (details.active) {
            totalPrefs++;
            if (details.matched) {
              matchCount++;
              matchesList.push(key === 'size' ? 'weight' : key);
            }
          }
        });

        if (matchCount === totalPrefs) {
          whyFitDesc.textContent = `🎯 Match Fit: ${currentDogName} matches all of your preferences!`;
          whyFitCard.className = 'details-fit-container';
        } else if (matchCount > 0) {
          whyFitDesc.textContent = `🐾 Good Fit: Meets criteria for ${matchesList.join(' & ')}.`;
          whyFitCard.className = 'details-fit-container warning';
        } else {
          whyFitDesc.textContent = '💝 Special Fit: Ready to surprise you with love.';
          whyFitCard.className = 'details-fit-container warning';
        }
      }
    }
  }
}

// ─── renderTraitChips: Important facts as pill badges ────────────────────────

function renderTraitChips(dog) {
  const secPersonality = document.getElementById('secPersonality');
  if (secPersonality) {
    secPersonality.style.display = 'block';
    secPersonality.removeAttribute('aria-hidden');
  }

  const traitChipsContainer = document.getElementById('traitChipsContainer');
  if (!traitChipsContainer) return;

  traitChipsContainer.innerHTML = '';

  // Clean up any existing facts toggle button
  const existingToggle = traitChipsContainer.parentNode.querySelector('.facts-toggle-btn');
  if (existingToggle) existingToggle.remove();

  const facts = dog.important_facts || [];

  if (facts.length > 0) {
    facts.forEach((fact) => {
      const chip = document.createElement('span');
      chip.className = 'trait-chip';
      chip.textContent = fact;
      traitChipsContainer.appendChild(chip);
    });
  } else {
    // Default trait chips when no facts exist
    ['Ask About House Training', 'Ask About Other Pets', 'Ask About Special Needs'].forEach(t => {
      const chip = document.createElement('span');
      chip.className = 'trait-chip';
      chip.textContent = t;
      traitChipsContainer.appendChild(chip);
    });
  }
}

// ─── renderBioSection: Meet [Dog] biography with truncation ─────────────────

function renderBioSection(dog) {
  const bioText = (dog.intro_summary || dog.description || dog.bio || '').trim();
  const aboutDogCard = document.getElementById('aboutDogCard');
  const aboutDogName = document.getElementById('aboutDogName');
  const aboutDogText = document.getElementById('aboutDogText');

  if (!aboutDogCard || !aboutDogText || !aboutDogName) return;

  if (bioText) {
    aboutDogCard.style.display = 'block';
    aboutDogName.textContent = currentDogName;
    aboutDogText.textContent = bioText;
    aboutDogText.classList.remove('collapsed');
  } else {
    aboutDogCard.style.display = 'none';
  }
}

// ─── initDogChat: Chat intro card, history loading, resume banner ────────────

async function initDogChat(dog, loadOptions, fetchId, isStaleFetch) {
  chatHistory.innerHTML = '';

  const introCard = document.createElement('div');
  introCard.className = 'chat-intro-card';
  introCard.id = 'chatIntroCard';
  if (loadOptions.resumeChat) {
    introCard.innerHTML = `
    <div class="chat-intro-title">💬 Continuing your chat with ${currentDogName} 🐾</div>
    <p class="chat-intro-text" style="color:var(--teal);">✓ Loading your previous conversation...</p>`;
  } else {
    introCard.innerHTML = `
    <div class="chat-intro-title">💬 Chat with ${currentDogName}</div>
    <p class="chat-intro-text">Start a chat with ${currentDogName}! Ask me anything about my personality, energy, or training.</p>
    <div class="chat-intro-disclaimer">
      🔒 Chats are AI-generated using shelter profile details and may be saved so you can continue them later. Avoid sharing sensitive personal info. Always confirm medical, behavioral, and adoption details with the shelter. <a href="/privacy.html" style="color:var(--teal); text-decoration:underline;">Privacy</a>
    </div>`;
  }
  introCard.style.display = 'none';
  chatHistory.appendChild(introCard);

  // Load chat history if resuming
  let resumeMsgsLoaded = 0;
  if (loadOptions.resumeChat && userEmail && currentAnimalId) {
    try {
      const histRes = await fetch(
        `/api/chat_history?email=${encodeURIComponent(userEmail)}&animal_id=${encodeURIComponent(currentAnimalId)}`
      );
      if (isStaleFetch()) return;
      if (histRes.ok) {
        const histData = await histRes.json();
        if (isStaleFetch()) return;
        const msgs = (histData.messages || []).filter(m => m.role !== 'system');
        resumeMsgsLoaded = msgs.length;
        conversationHistory = [];
        msgs.forEach(m => {
          appendMessage(
            m.role === 'assistant' ? 'bot' : 'user',
            m.content,
            m.role === 'assistant' ? currentDogName.charAt(0).toUpperCase() : undefined,
            false
          );
        });
        const introP = introCard.querySelector('p');
        if (introP) {
          introP.textContent = msgs.length > 0
            ? `✓ ${msgs.length} message${msgs.length !== 1 ? 's' : ''} loaded — keep chatting!`
            : 'Start a new conversation!';
          introP.style.color = 'var(--teal)';
        }
        trackEvent('resume_chat_loaded', { dog_name: currentDogName, animal_id: currentAnimalId, msg_count: msgs.length });
      }
    } catch (e) {
      console.warn('Failed to load chat history:', e);
    }
  }

  if (isStaleFetch()) return;

  // Send initial greeting
  if (!loadOptions.resumeChat || resumeMsgsLoaded === 0) {
    const firstLetter = currentDogName.charAt(0).toUpperCase();
    appendMessage('bot', `Hi there! I'm ${currentDogName}. Ask me anything!`, firstLetter, false);
  }

  // Check for previous chat — show resume banner (non-blocking)
  if (!loadOptions.resumeChat && userEmail && currentAnimalId) {
    const resumeBannerFetchId = fetchId;
    (async () => {
      try {
        const histCheck = await fetch(
          `/api/chat_history?email=${encodeURIComponent(userEmail)}&animal_id=${encodeURIComponent(currentAnimalId)}`
        );
        if (resumeBannerFetchId !== activeDogFetchId) return;
        if (!histCheck.ok) return;
        const histData = await histCheck.json();
        if (resumeBannerFetchId !== activeDogFetchId) return;
        const prevMsgs = (histData.messages || []).filter(m => m.role !== 'system');
        if (prevMsgs.length > 0) {
          const resumeBanner = document.createElement('div');
          resumeBanner.id = 'resumeChatBanner';
          resumeBanner.style.cssText = `
            display:flex; align-items:center; justify-content:space-between; gap:12px;
            background:rgba(20,184,166,0.08); border:1.5px solid rgba(20,184,166,0.25);
            border-radius:14px; padding:12px 14px; margin:8px 0;
            font-size:0.82rem; color:var(--text-muted); animation:fadeIn 0.3s ease;
          `;
          resumeBanner.innerHTML = `
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:1.1rem;">💬</span>
              <div>
                <div style="font-weight:800; color:var(--teal); font-size:0.83rem;">Previous chat found</div>
                <div style="font-size:0.76rem; margin-top:1px;">${prevMsgs.length} message${prevMsgs.length !== 1 ? 's' : ''} from your last visit</div>
              </div>
            </div>
            <button id="loadPrevChatBtn" style="
              padding:7px 14px; background:var(--teal); color:var(--accent-text);
              border:none; border-radius:20px; font-weight:800; font-size:0.76rem;
              cursor:pointer; white-space:nowrap; flex-shrink:0;
              box-shadow:0 4px 10px rgba(20,184,166,0.25);
            ">Load Chat ↩</button>
          `;
          chatHistory.insertBefore(resumeBanner, chatHistory.children[1] || null);

          document.getElementById('loadPrevChatBtn').addEventListener('click', async () => {
            resumeBanner.innerHTML = '<div style="padding:6px 0; color:var(--teal); font-size:0.82rem; font-weight:700;">⏳ Loading your previous conversation...</div>';
            const lastChild = chatHistory.lastElementChild;
            if (lastChild && lastChild !== resumeBanner && lastChild !== introCard) {
              lastChild.remove();
            }
            conversationHistory = [];
            prevMsgs.forEach(m => {
              appendMessage(
                m.role === 'assistant' ? 'bot' : 'user',
                m.content,
                m.role === 'assistant' ? currentDogName.charAt(0).toUpperCase() : undefined,
                false
              );
            });
            resumeBanner.remove();
            scrollToBottom();
            trackEvent('resume_chat_loaded', { dog_name: currentDogName, animal_id: currentAnimalId, msg_count: prevMsgs.length });
          });
        }
      } catch (e) {
        // Non-blocking — ignore errors silently
      }
    })();
  }
}

// ─── fetchRandomDog: Main orchestrator ──────────────────────────────────────

async function fetchRandomDog(forcedAnimalId = null, loadOptions = {}) {
  const fetchId = ++activeDogFetchId;
  const isStaleFetch = () => fetchId !== activeDogFetchId;

  // Save current dog as previous (skip when navigating back)
  const isGoingBack = previousDogId && forcedAnimalId === previousDogId;
  if (currentAnimalId && !isGoingBack) {
    previousDogId = currentAnimalId;
  }
  updateBackBtnVisibility();

  setAppState('loading');
  if (typeof exitChatMode === 'function') exitChatMode();
  window.scrollTo(0, 0);

  resetProfileUI();

  try {
    const response = await fetchDogData(forcedAnimalId);
    if (isStaleFetch()) return;

    if (!response.ok) {
      if (forcedAnimalId) {
        if (!isStaleFetch()) showDogUnavailableState(fetchId);
        return;
      }
      try {
        const errBody = await response.json();
        if (errBody.no_matches) {
          if (!isStaleFetch()) setAppState('empty');
          return;
        }
      } catch (_) {}
      throw new Error('Failed to fetch a dog.');
    }

    const dog = await response.json();
    if (isStaleFetch()) return;

    // Update global state
    currentDogData = dog;
    currentAnimalId = dog.animal_id;
    if (currentAnimalId && !viewedIds.includes(currentAnimalId)) {
      viewedIds.push(currentAnimalId);
    }
    updateBackBtnVisibility();

    // Update document metadata & URL
    updateDocumentMetaForDog(dog);
    if (dog.animal_id) updateDogShareUrl(dog.animal_id, true);

    // Sync location dropdown
    syncLocationDropdown(dog, forcedAnimalId);

    // Render all profile sections
    renderDogProfile(dog);
    renderCompatBadges(dog);
    renderTraitChips(dog);
    renderBioSection(dog);

    // Initialize chat suggestions
    initSuggestionsForDog(dog);
    updateSuggestions();

    // Initialize chat
    await initDogChat(dog, loadOptions, fetchId, isStaleFetch);

    if (!isStaleFetch()) {
      setAppState('dog_loaded');
      trackEvent('dog_viewed', { dog_name: currentDogName, animal_id: currentAnimalId });
    }
  } catch (err) {
    if (isStaleFetch()) return;
    console.error(err);
    setAppState('empty');
    dogName.textContent = '';
  }
}
