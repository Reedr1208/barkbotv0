// ─── Dog Profile Loading ────────────────────────────────────────────────────
// fetchRandomDog, favorite handling, and marked configuration

// Configure marked options to be safe
marked.setOptions({
  breaks: true,
  gfm: true,
  headerIds: false
});


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
if (chatInput && !localStorage.getItem('has_interacted_with_chat')) {
  chatInput.classList.add('attention-pulse');
  if (chatInputWrapper) chatInputWrapper.classList.add('attention-wrapper');
}
const sendBtn = document.getElementById('sendBtn');

const favBtn = document.getElementById('favBtn');
const scrollContent = document.getElementById('scrollContent');

// stopFactsAnimation is defined in ui.js

// Toggle active favorite heart (local + backend sync)
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
        // Non-blocking: localStorage is already updated
        console.warn('Favorites sync failed:', e);
      }
    }
  });
}

// formatRelativeTime is defined in utils.js

async function fetchRandomDog(forcedAnimalId = null, loadOptions = {}) {
  const fetchId = ++activeDogFetchId;
  const isStaleFetch = () => fetchId !== activeDogFetchId;

  setAppState('loading');
  if (typeof exitChatMode === 'function') {
exitChatMode();
  }
  window.scrollTo(0, 0);

  // Reset issue reporter button
  const reportIssueBtn = document.getElementById('reportIssueBtn');
  if (reportIssueBtn) {
reportIssueBtn.textContent = 'Report an issue';
reportIssueBtn.disabled = false;
reportIssueBtn.style.color = 'var(--accent)';
reportIssueBtn.style.textDecoration = 'underline';
reportIssueBtn.style.cursor = 'pointer';
  }

  // Clear current state instantly to prevent lagging info
  dogImage.src = '';
  dogName.textContent = '';
  dogId.textContent = '';
  const locationTextEl = document.getElementById('dogLocationText');
  if (locationTextEl) locationTextEl.textContent = '';
  const dogBreedEl = document.getElementById('dogBreed');
  if (dogBreedEl) dogBreedEl.textContent = 'Rescue Mix 🐾';
  const lastCheckedEl = document.getElementById('lastCheckedDate');
  if (lastCheckedEl) lastCheckedEl.textContent = 'Today';
  dogAge.textContent = '';
  dogWeight.textContent = '';

  // Reset rotate overlay properties
  const rotateDogPhoto = document.getElementById('rotateDogPhoto');
  const rotateDogTitle = document.getElementById('rotateDogTitle');
  const rotateDogText = document.getElementById('rotateDogText');
  if (rotateDogPhoto) rotateDogPhoto.src = 'happy_rescue_pup.png';
  if (rotateDogTitle) rotateDogTitle.innerHTML = `Find your perfect match! 🐶`;
  if (rotateDogText) rotateDogText.textContent = `ChattyHound is optimized for portrait mode. Spin your device around to continue finding and chatting with shelter dogs! 🐾`;

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

  // Hide custom whyFitCard
  const whyFitCard = document.getElementById('whyFitCard');
  if (whyFitCard) whyFitCard.style.display = 'none';

  // Reset combined preference metadata rows
  const statBoxes = ['chipGender', 'chipAge', 'chipWeight'];
  statBoxes.forEach(id => {
const el = document.getElementById(id);
if (el) {
  el.className = 'detail-chip';
}
  });
  const compatDots = ['dotGender', 'dotAge', 'dotWeight', 'dotLocation'];
  compatDots.forEach(id => {
const el = document.getElementById(id);
if (el) {
  el.style.display = 'none';
  el.className = 'compat-dot';
}
  });
  const prefNotes = ['noteGender', 'noteAge', 'noteWeight'];
  prefNotes.forEach(id => {
const el = document.getElementById(id);
if (el) {
  el.style.display = 'none';
  el.innerHTML = '';
}
  });
  const dogGender = document.getElementById('dogGender');
  if (dogGender) dogGender.textContent = '';

  profilePanel.classList.add('loading');

  try {
// Ensure browser geolocation has resolved before first fetch
if (!userCoords) {
  const geoResult = await _geoCoordsPromise;
  if (geoResult) userCoords = geoResult;
}

let url = '/api/random_dog?';
const params = [];
if (forcedAnimalId) {
  params.push('animal_id=' + encodeURIComponent(forcedAnimalId));
} else if (viewedIds.length > 0) {
  params.push('viewed=' + viewedIds.join(','));
}
if (userEmail) params.push('email=' + encodeURIComponent(userEmail));
if (currentPrefs.gender && currentPrefs.gender !== 'any') params.push('gender=' + encodeURIComponent(currentPrefs.gender));
if (currentPrefs.age_group && currentPrefs.age_group !== 'any') params.push('age_group=' + encodeURIComponent(currentPrefs.age_group));
if (currentPrefs.size && currentPrefs.size !== 'any') params.push('size=' + encodeURIComponent(currentPrefs.size));
if (currentPrefs.location && currentPrefs.location !== 'any') params.push('location=' + encodeURIComponent(currentPrefs.location));
if (userCoords) {
  params.push('lat=' + userCoords.lat);
  params.push('lon=' + userCoords.lon);
}
url += params.join('&');

const response = await fetch(url);
if (isStaleFetch()) return;

if (!response.ok) {
  if (forcedAnimalId) {
    if (!isStaleFetch()) showDogUnavailableState(fetchId);
    return;
  }
  throw new Error('Failed to fetch a dog.');
}

const dog = await response.json();
if (isStaleFetch()) return;

currentDogData = dog;
updateDocumentMetaForDog(dog);

if (!dog.user_has_preferences) {
  const hs = document.getElementById('headerLocationSelect');
  if (hs && hs.value === 'any') {
    if (dog.suggested_location && window.__CH_LOCATIONS_DATA__) {
      const locObj = window.__CH_LOCATIONS_DATA__.find(l => l.display_name === dog.suggested_location);
      if (locObj) {
        hs.value = locObj.relative_path;
      } else {
        hs.value = 'all';
      }
    } else {
      hs.value = 'all';
    }
  }
}

if (dog.animal_id) {
  updateDogShareUrl(dog.animal_id, true);
}

currentAnimalId = dog.animal_id;
if (currentAnimalId && !viewedIds.includes(currentAnimalId)) {
  viewedIds.push(currentAnimalId);
}

// Toggle Favorite heart state on load
if (favBtn) {
  if (favoritesList.includes(currentAnimalId)) {
    favBtn.classList.add('favorited');
  } else {
    favBtn.classList.remove('favorited');
  }
}

// Handle preference match badge
const badgeContainer = document.getElementById('prefMatchBadgeContainer');
if (badgeContainer) {
  badgeContainer.innerHTML = '';
  if (dog.user_has_preferences) {
    if (dog.preferences_matched) {
      badgeContainer.innerHTML = '<span class="match-badge"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" style="margin-right:2px;"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg> Strong Match</span>';
    } else {
      badgeContainer.innerHTML = '<span class="match-badge fallback" title="Showing all pups as no exact fits match your preferences currently.">All Pups</span>';
    }
  }
}

currentDogName = dog.name || 'this dog';
dogName.textContent = dog.name || 'Unknown';
const dogBreedEl = document.getElementById('dogBreed');
if (dogBreedEl) {
  let breedText = dog.breed_or_description || 'Rescue Mix';
  if (breedText.toLowerCase() === 'unknown') breedText = 'Unknown breed';
  dogBreedEl.textContent = breedText + ' 🐾';
}
chatTitleName.textContent = currentDogName;
const idParts = dog.animal_id ? dog.animal_id.split('-') : [];
const nativeId = idParts.length > 1 ? idParts.slice(1).join('-') : dog.animal_id;
const shelterId = idParts.length > 0 ? idParts[0] : '';
dogId.textContent = dog.animal_id ? `${nativeId} • ${shelterId}` : '';
if (locationTextEl) {
  locationTextEl.textContent = dog.shelter_name || 'Pima Animal Care Center';
}
const lastCheckedEl = document.getElementById('lastCheckedDate');
if (lastCheckedEl) {
  lastCheckedEl.textContent = formatRelativeTime(dog.info_refreshed_at);
}

// Populate rotate overlay with current dog details
const rotateDogPhoto = document.getElementById('rotateDogPhoto');
const rotateDogTitle = document.getElementById('rotateDogTitle');
const rotateDogText = document.getElementById('rotateDogText');
if (rotateDogPhoto) {
  rotateDogPhoto.src = dog.shelter_image_url || (dog.image_file ? (dog.image_base_url + dog.image_file) : 'happy_rescue_pup.png');
}
if (rotateDogTitle) {
  rotateDogTitle.innerHTML = `Let's chat with <span style="color:var(--accent-hover);">${currentDogName}</span>! 🐾`;
}
if (rotateDogText) {
  rotateDogText.textContent = `To interact with ${currentDogName} or see more profile details, spin your device back to portrait mode!`;
}

// Dynamically update dog name in buttons, labels, and placeholders
const askBtnTitle = document.getElementById('askBtnTitle');
if (askBtnTitle) askBtnTitle.textContent = "Ask " + currentDogName;
if (favBtn) {
  const isFav = favoritesList.includes(currentAnimalId);
  favBtn.setAttribute('aria-label', isFav ? `Remove ${currentDogName} from My Dogs` : `Save ${currentDogName} to My Dogs`);
}
if (paccLink) {
  paccLink.setAttribute('aria-label', `Open ${currentDogName}'s official shelter page on 24Petconnect`);
}
updateShareButtonLabels();
if (chatInput) chatInput.placeholder = "Ask about me!";

// Update sticky dog bar
const stickyDogName = document.getElementById('stickyDogName');
const stickyDogMeta = document.getElementById('stickyDogMeta');
if (stickyDogName) stickyDogName.textContent = currentDogName;
if (stickyDogMeta) {
  const agePart = cleanAgeText(dog.age || '');
  const weightPart = cleanWeightText(dog.weight || '');
  const parts = [agePart, weightPart].filter(p => p && p !== '-');
  stickyDogMeta.textContent = parts.join(' · ') || 'Shelter Dog';
}

// Fill actual values in the stats panel (using compact cleaning functions)
const genderEl = document.getElementById('dogGender');
if (genderEl) genderEl.textContent = dog.sex || cleanGenderText(dog.gender || 'Unknown');
dogAge.textContent = dog.age_summary || cleanAgeText(dog.age || 'Unknown');
dogWeight.textContent = dog.weight_summary || cleanWeightText(dog.weight || 'Unknown');

// Restore action overlays on successful load
const mobileActionBar = document.getElementById('mobileActionBar');
if (mobileActionBar) mobileActionBar.style.display = 'flex';
const stickyDogBar = document.getElementById('stickyDogBar');
if (stickyDogBar) stickyDogBar.style.display = 'flex';

// ──── CLIENT-SIDE LIFESTYLE COMPATIBILITY ENGINE & MATCH SENTENCE GENERATOR ────
let lifestyleSummary = '';
const dogWeightNum = parseFloat(cleanWeightText(dog.weight || ''));
const factsLower = (dog.important_facts || []).map(f => f.toLowerCase().trim());
const descLower = (dog.description || dog.bio || '').toLowerCase();

if (dogWeightNum && dogWeightNum < 25) {
  if (descLower.includes('calm') || descLower.includes('couch') || descLower.includes('gentle')) {
    lifestyleSummary = `A perfect gentle lapdog ideal for a cozy apartment environment.`;
  } else {
    lifestyleSummary = `A lively, compact companion ready for fun walks and small spaces.`;
  }
} else if (descLower.includes('active') || descLower.includes('hike') || descLower.includes('run') || descLower.includes('energy') || factsLower.some(f => f.includes('energy') || f.includes('active'))) {
  lifestyleSummary = `A magnificent high-energy adventure partner perfect for active hikers and yard playtime.`;
} else if (descLower.includes('kid') || descLower.includes('child') || descLower.includes('family') || factsLower.some(f => f.includes('kid') || f.includes('family'))) {
  lifestyleSummary = `A sweet-natured family sweetheart who loves playtime and gentle social environments.`;
} else {
  lifestyleSummary = `A loyal and loving companion with a wonderful personality ready to bond deeply with you.`;
}

// Update stat row backgrounds and dots based on preferences
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

    const whyFitDesc = document.getElementById('whyFitDesc');
    if (whyFitCard && whyFitDesc) {
      whyFitCard.style.display = 'block';

      let matchCount = 0;
      let totalPrefs = 0;
      const matchesList = [];
      const mismatchesList = [];

      Object.keys(dog.match_details).forEach(key => {
        const details = dog.match_details[key];
        if (details.active) {
          totalPrefs++;
          const formattedKey = key === 'size' ? 'weight' : key;
          if (details.matched) {
            matchCount++;
            matchesList.push(formattedKey);
          } else {
            mismatchesList.push(formattedKey);
          }
        }
      });

      if (matchCount === totalPrefs) {
        whyFitDesc.textContent = `🎯 Match Fit: ${lifestyleSummary} ${currentDogName} matches all of your preferences!`;
        whyFitCard.className = 'details-fit-container';
      } else if (matchCount > 0) {
        whyFitDesc.textContent = `🐾 Good Fit: ${lifestyleSummary} Meets criteria for ${matchesList.join(' & ')}.`;
        whyFitCard.className = 'details-fit-container warning';
      } else {
        whyFitDesc.textContent = `💝 Special Fit: ${lifestyleSummary} Ready to surprise you with love.`;
        whyFitCard.className = 'details-fit-container warning';
      }
    }
  }
}

// Show observations section on successful load
const secPersonality = document.getElementById('secPersonality');
if (secPersonality) {
  secPersonality.style.display = 'block';
  secPersonality.removeAttribute('aria-hidden');
}

// Render Trait Chips from dog.important_facts
const traitChipsContainer = document.getElementById('traitChipsContainer');
if (traitChipsContainer) {
  traitChipsContainer.innerHTML = '';
  
  // Clean up any existing facts toggle button
  const existingToggle = traitChipsContainer.parentNode.querySelector('.facts-toggle-btn');
  if (existingToggle) {
    existingToggle.remove();
  }

  const facts = dog.important_facts || [];
  if (facts.length > 0) {
    const MAX_VISIBLE_FACTS = 3;
    facts.forEach((fact, index) => {
      const chip = document.createElement('span');
      chip.className = 'trait-chip';
      if (index >= MAX_VISIBLE_FACTS) {
        chip.classList.add('fact-hidden');
        chip.style.display = 'none';
      }
      chip.textContent = fact;
      traitChipsContainer.appendChild(chip);
    });

    if (facts.length > MAX_VISIBLE_FACTS) {
      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'see-more-toggle facts-toggle-btn';
      toggleBtn.style.width = '100%';
      toggleBtn.style.justifyContent = 'center';
      toggleBtn.style.marginTop = '8px';
      toggleBtn.innerHTML = `See more notes (${facts.length - MAX_VISIBLE_FACTS} more) <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 2px;"><polyline points="6 9 12 15 18 9"/></svg>`;
      
      let factsExpanded = false;
      toggleBtn.addEventListener('click', () => {
        factsExpanded = !factsExpanded;
        const hiddenChips = traitChipsContainer.querySelectorAll('.trait-chip.fact-hidden');
        hiddenChips.forEach(chip => {
          chip.style.display = factsExpanded ? 'inline-flex' : 'none';
        });
        if (factsExpanded) {
          toggleBtn.innerHTML = `See less notes <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 2px;"><polyline points="18 15 12 9 6 15"/></svg>`;
        } else {
          toggleBtn.innerHTML = `See more notes (${facts.length - MAX_VISIBLE_FACTS} more) <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 2px;"><polyline points="6 9 12 15 18 9"/></svg>`;
        }
      });
      traitChipsContainer.after(toggleBtn);
    }
  } else {
    // Default friendly trait chips if no specific scraper facts
    const defaultTraits = ["Active & Playful", "Friendly Companion", "Sweet Personality", "Shelter Hero"];
    defaultTraits.forEach(t => {
      const chip = document.createElement('span');
      chip.className = 'trait-chip';
      chip.textContent = t;
      traitChipsContainer.appendChild(chip);
    });
  }
}

// Render Shelter Biography Story
const bioText = (dog.intro_summary || dog.description || dog.bio || '').trim();
const aboutDogCard = document.getElementById('aboutDogCard');
const aboutDogName = document.getElementById('aboutDogName');
const aboutDogText = document.getElementById('aboutDogText');
const aboutDogToggle = document.getElementById('aboutDogToggle');

if (aboutDogCard && aboutDogText && aboutDogToggle && aboutDogName) {
  if (bioText) {
    aboutDogCard.style.display = 'block';
    aboutDogName.textContent = currentDogName;
    
    // Save full text in dataset for robust JS toggle
    aboutDogText.dataset.fullBio = bioText;

    // Check if description warrants a "See more" toggle using JS-based truncation
    if (bioText.length > 180) {
      aboutDogText.textContent = bioText.slice(0, 180) + '...';
      aboutDogToggle.style.display = 'inline-flex';
      aboutDogToggle.innerHTML = `See more <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 2px;"><polyline points="6 9 12 15 18 9"/></svg>`;
      aboutDogText.classList.add('collapsed');
    } else {
      aboutDogText.textContent = bioText;
      aboutDogToggle.style.display = 'none';
      aboutDogText.classList.remove('collapsed');
    }
  } else {
    aboutDogCard.style.display = 'none';
  }
}

if (dog.shelter_profile_url) {
  paccLink.href = dog.shelter_profile_url;
  paccLink.style.display = 'inline-flex';
}

// Update sticky avatar image
const stickyDogAvatar = document.getElementById('stickyDogAvatar');
if (stickyDogAvatar) {
  if (dog.image_file && dog.image_base_url) {
    stickyDogAvatar.src = dog.image_base_url + dog.image_file;
  } else if (dog.shelter_image_url) {
    stickyDogAvatar.src = dog.shelter_image_url;
  } else if (dog.shelter_image_url) {
    stickyDogAvatar.src = dog.shelter_image_url;
  } else {
    stickyDogAvatar.src = '';
  }
}

// Handle Image
if (dog.image_file && dog.image_base_url) {
  dogImage.src = dog.image_base_url + dog.image_file;
} else if (dog.shelter_image_url) {
  dogImage.src = dog.shelter_image_url;
} else if (dog.shelter_image_url) {
  dogImage.src = dog.shelter_image_url;
}

const mobileAdoptBtn = document.getElementById('mobileAdoptBtn');
if (mobileAdoptBtn && dog.shelter_profile_url) {
  mobileAdoptBtn.href = dog.shelter_profile_url;
}

const stickyShelterBtn = document.getElementById('stickyShelterBtn');
if (stickyShelterBtn && dog.shelter_profile_url) {
  stickyShelterBtn.href = dog.shelter_profile_url;
}

chatInput.disabled = false;
sendBtn.disabled = false;

// ──── CLIENT-SIDE LIFESTYLE COMPATIBILITY ENGINE ────
let fitBadgeType = 'cuddle';
let fitBadgeLabel = 'Sweet cuddle companion 💖';
const parsedWeight = parseFloat(cleanWeightText(dog.weight || ''));

if (parsedWeight && parsedWeight < 25 && !descLower.includes('high energy') && !descLower.includes('active home')) {
  fitBadgeType = 'apartment';
  fitBadgeLabel = 'Great apartment fit 🏠';
} else if (descLower.includes('active') || descLower.includes('hike') || descLower.includes('run') || descLower.includes('high energy') || factsLower.some(f => f.includes('energy') || f.includes('active'))) {
  fitBadgeType = 'adventure';
  fitBadgeLabel = 'High-energy adventure buddy ⛰️';
} else if (descLower.includes('kid') || descLower.includes('child') || descLower.includes('family') || factsLower.some(f => f.includes('kid') || f.includes('family'))) {
  fitBadgeType = 'family';
  fitBadgeLabel = 'Kid & family friendly 👼';
} else if (descLower.includes('cat') || factsLower.some(f => f.includes('cat'))) {
  fitBadgeType = 'cats';
  fitBadgeLabel = 'Cat-friendly companion 🐱';
} else if (descLower.includes('calm') || descLower.includes('sweet') || descLower.includes('gentle') || descLower.includes('couch')) {
  fitBadgeType = 'cuddle';
  fitBadgeLabel = 'Gentle couch snuggler 🛌';
}

const matchBadgeContainer = document.getElementById('prefMatchBadgeContainer');
if (matchBadgeContainer) {
  const fitBadgeHtml = `<span class="fit-badge-tag ${fitBadgeType}">${fitBadgeLabel}</span>`;
  matchBadgeContainer.innerHTML = fitBadgeHtml + matchBadgeContainer.innerHTML;
}

// Initialize dynamic, context-aware prompt suggestions
updateSuggestions();

// Build the Chat Intro Welcome Card
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
    🔒 ChattyHound uses available shelter profile details to help you get to know each dog. Always confirm medical, behavioral, and adoption details directly with shelter staff.
  </div>`;
}
introCard.style.display = 'none'; // Hidden by default in chat-engaged mode
chatHistory.appendChild(introCard);

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

if (!loadOptions.resumeChat) {
  const firstLetter = currentDogName.charAt(0).toUpperCase();
  appendMessage('bot', `Hi there! I'm ${currentDogName}. Ask me anything!`, firstLetter, false);
} else if (resumeMsgsLoaded === 0) {
  const firstLetterResume = currentDogName.charAt(0).toUpperCase();
  appendMessage('bot', `Hi there! I'm ${currentDogName}. Ask me anything!`, firstLetterResume, false);
}

// Check if user has a previous chat with this dog — show resume banner if so
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
        // Inject a resume banner before the greeting message
        const resumeBanner = document.createElement('div');
        resumeBanner.id = 'resumeChatBanner';
        resumeBanner.style.cssText = `
        display: flex; align-items: center; justify-content: space-between; gap: 12px;
        background: rgba(20, 184, 166, 0.08); border: 1.5px solid rgba(20, 184, 166, 0.25);
        border-radius: 14px; padding: 12px 14px; margin: 8px 0;
        font-size: 0.82rem; color: var(--text-muted); animation: fadeIn 0.3s ease;
      `;
        resumeBanner.innerHTML = `
        <div style="display:flex; align-items:center; gap: 8px;">
          <span style="font-size:1.1rem;">💬</span>
          <div>
            <div style="font-weight:800; color: var(--teal); font-size:0.83rem;">Previous chat found</div>
            <div style="font-size:0.76rem; margin-top:1px;">${prevMsgs.length} message${prevMsgs.length !== 1 ? 's' : ''} from your last visit</div>
          </div>
        </div>
        <button id="loadPrevChatBtn" style="
          padding: 7px 14px; background: var(--teal); color: var(--accent-text);
          border: none; border-radius: 20px; font-weight: 800; font-size: 0.76rem;
          cursor: pointer; white-space: nowrap; flex-shrink: 0;
          box-shadow: 0 4px 10px rgba(20,184,166,0.25);
        ">Load Chat ↩</button>
      `;
        // Insert after introCard
        chatHistory.insertBefore(resumeBanner, chatHistory.children[1] || null);

        document.getElementById('loadPrevChatBtn').addEventListener('click', async () => {
          resumeBanner.innerHTML = `<div style="padding:6px 0; color:var(--teal); font-size:0.82rem; font-weight:700;">⏳ Loading your previous conversation...</div>`;
          // Clear current greeting and load history
          // Remove the greeting bubble (last child before we add history)
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
          // Scroll to latest message
          scrollToBottom();
          trackEvent('resume_chat_loaded', { dog_name: currentDogName, animal_id: currentAnimalId, msg_count: prevMsgs.length });
        });
      }
    } catch (e) {
      // Non-blocking — ignore errors silently
    }
  })();
}

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
