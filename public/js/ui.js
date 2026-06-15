// ─── UI State Management ────────────────────────────────────────────────────
// Core UI state transitions, view switching, toasts, and DOM meta updates

function setAppState(state) {
  const profilePanel = document.getElementById('profilePanel');
  const dogUnavailableCard = document.getElementById('dogUnavailableCard');
  const emptyStateCard = document.getElementById('emptyStateCard');
  const detailsBox = document.getElementById('detailsBox');
  const ctaGrid = document.querySelector('.cta-grid');
  const chatSection = document.getElementById('chatSection');
  const heroSection = document.querySelector('.hero-section');
  const mobileActionBar = document.getElementById('mobileActionBar');
  const stickyDogBar = document.getElementById('stickyDogBar');

  const setDisplay = (el, val) => { 
    if (el) {
      el.style.display = val; 
      if (val === 'none') {
        el.setAttribute('aria-hidden', 'true');
      } else {
        el.removeAttribute('aria-hidden');
      }
    }
  };

  if (profilePanel) {
    profilePanel.classList.remove('loading-skeleton');
    profilePanel.classList.remove('loading');
  }

  if (state === 'loading') {
    if (profilePanel) {
      profilePanel.classList.add('loading-skeleton');
      profilePanel.classList.add('loading');
    }
    setDisplay(dogUnavailableCard, 'none');
    setDisplay(emptyStateCard, 'none');
    setDisplay(detailsBox, 'flex');
    setDisplay(ctaGrid, 'none');
    setDisplay(chatSection, 'none');
    setDisplay(heroSection, 'block');
    setDisplay(mobileActionBar, 'none');
    if (stickyDogBar) {
      stickyDogBar.style.display = 'none';
      stickyDogBar.classList.remove('visible');
      stickyDogBar.setAttribute('aria-hidden', 'true');
    }
  } else if (state === 'dog_loaded') {
    setDisplay(dogUnavailableCard, 'none');
    setDisplay(emptyStateCard, 'none');
    setDisplay(detailsBox, 'flex');
    setDisplay(ctaGrid, 'grid');
    setDisplay(chatSection, 'flex');
    setDisplay(heroSection, 'block');
    setDisplay(mobileActionBar, 'flex');
  } else if (state === 'empty') {
    setDisplay(dogUnavailableCard, 'none');
    setDisplay(emptyStateCard, 'flex');
    setDisplay(detailsBox, 'none');
    setDisplay(ctaGrid, 'none');
    setDisplay(chatSection, 'none');
    setDisplay(heroSection, 'none');
    setDisplay(mobileActionBar, 'none');
    if (stickyDogBar) {
      stickyDogBar.style.display = 'none';
      stickyDogBar.classList.remove('visible');
      stickyDogBar.setAttribute('aria-hidden', 'true');
    }
  } else if (state === 'unavailable') {
    setDisplay(dogUnavailableCard, 'flex');
    setDisplay(emptyStateCard, 'none');
    setDisplay(detailsBox, 'none');
    setDisplay(ctaGrid, 'none');
    setDisplay(chatSection, 'none');
    setDisplay(heroSection, 'none');
    setDisplay(mobileActionBar, 'none');
    if (stickyDogBar) {
      stickyDogBar.style.display = 'none';
      stickyDogBar.classList.remove('visible');
      stickyDogBar.setAttribute('aria-hidden', 'true');
    }
  }
}

function showToast(message) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.className = 'toast-notification';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<span>🐾</span> ${message}`;
  toast.classList.add('visible');
  if (toast.timeoutId) {
    clearTimeout(toast.timeoutId);
  }
  toast.timeoutId = setTimeout(() => {
    toast.classList.remove('visible');
  }, 3000);
}

function showDogUnavailableState(fetchId) {
  setAppState('unavailable');
  const profilePanel = document.getElementById('profilePanel');
  if (profilePanel) {
    profilePanel.classList.remove('loading');
    profilePanel.classList.remove('loading-skeleton');
  }
  const rotateDogPhoto = document.getElementById('rotateDogPhoto');
  const rotateDogTitle = document.getElementById('rotateDogTitle');
  const rotateDogText = document.getElementById('rotateDogText');
  if (rotateDogPhoto) rotateDogPhoto.src = 'happy_rescue_pup.png';
  if (rotateDogTitle) rotateDogTitle.innerHTML = `Dog Unavailable 🐾`;
  if (rotateDogText) rotateDogText.textContent = `This pup is no longer available. Spin your device around to meet other adoptable dogs!`;
}

function updateDocumentMetaForDog(dog) {
  if (!dog || !dog.animal_id) return;
  const name = dog.name || 'this dog';
  const shelter = dog.shelter_name || 'Pima Animal Care Center';
  const pron = pronounForGender(dog.gender);
  const title = `Meet ${name} | ChattyHound`;
  const description = `${name} is an adoptable rescue dog at ${shelter}. Chat with ${pron} on ChattyHound and continue to the official shelter page.`;
  const canonical = getCanonicalDogUrl(dog.animal_id);
  const image = getDogImageUrl(dog);

  document.title = title;
  const descMeta = document.querySelector('meta[name="description"]');
  if (descMeta) descMeta.setAttribute('content', description);
  const canonicalLink = document.querySelector('link[rel="canonical"]');
  if (canonicalLink) canonicalLink.setAttribute('href', canonical);
  const ogPairs = [
    ['og:url', canonical],
    ['og:title', `Meet ${name} on ChattyHound`],
    ['og:description', description],
    ['og:image', image],
    ['og:image:secure_url', image],
    ['twitter:url', canonical],
    ['twitter:title', `Meet ${name} on ChattyHound`],
    ['twitter:description', description],
    ['twitter:image', image]
  ];
  ogPairs.forEach(([prop, content]) => {
    let el = document.querySelector(`meta[property="${prop}"]`);
    if (!el) {
      el = document.createElement('meta');
      el.setAttribute('property', prop);
      document.head.appendChild(el);
    }
    el.setAttribute('content', content);
  });
  let ogAlt = document.querySelector('meta[property="og:image:alt"]');
  if (!ogAlt) {
    ogAlt = document.createElement('meta');
    ogAlt.setAttribute('property', 'og:image:alt');
    document.head.appendChild(ogAlt);
  }
  ogAlt.setAttribute('content', `Meet ${name} on ChattyHound`);
}

// View Switching Utility
function switchView(viewName) {
  const landingView = document.getElementById('landingView');
  const appView = document.getElementById('appView');
  const footerInputBar = document.querySelector('.footer-input-bar');

  if (viewName === 'app') {
    landingView.classList.add('hidden');
    appView.classList.remove('hidden');
    if (footerInputBar) footerInputBar.style.display = 'block';
    localStorage.setItem('chattyhound_visited', 'true');
  } else {
    landingView.classList.remove('hidden');
    appView.classList.add('hidden');
    if (footerInputBar) footerInputBar.style.display = 'none';
  }
}

function enterChatMode() {
  document.body.classList.add('chat-engaged');
  const footerOverlay = document.getElementById('footerOverlay');
  if (footerOverlay) footerOverlay.style.display = 'none';

  setTimeout(() => {
    window.scrollTo(0, 0);
    scrollToBottom();
  }, 50);
}

function exitChatMode() {
  document.body.classList.remove('chat-engaged');
  const footerOverlay = document.getElementById('footerOverlay');
  if (footerOverlay) footerOverlay.style.display = 'block';
}

function scrollToBottom() {
  const scrollContent = document.getElementById('scrollContent');
  if (scrollContent && window.innerWidth < 800) {
    setTimeout(() => {
      scrollContent.scrollTop = scrollContent.scrollHeight;
    }, 50); // small delay to allow DOM updates (like prompt rendering)
  }
  const profileBody = document.querySelector('.profile-body');
  if (profileBody) {
    profileBody.scrollTop = profileBody.scrollHeight;
  }
}

function stopFactsAnimation() {
  // Stub left for safety/backward compatibility
}
