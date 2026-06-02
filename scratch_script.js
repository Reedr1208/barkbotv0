  window['_fs_host'] = 'fullstory.com';
  window['_fs_script'] = 'edge.fullstory.com/s/fs.js';
  window['_fs_org'] = 'ZKPBZ';
  window['_fs_namespace'] = 'FS';
  !function(m,n,e,t,l,o,g,y){var s,f,a=function(h){
  return!(h in m)||(m.console&&m.console.log&&m.console.log('FullStory namespace conflict. Please set window["_fs_namespace"].'),!1)}(e)
  ;function p(b){var h,d=[];function j(){h&&(d.forEach((function(b){var d;try{d=b[h[0]]&&b[h[0]](h[1])}catch(h){return void(b[3]&&b[3](h))}
  d&&d.then?d.then(b[2],b[3]):b[2]&&b[2](d)})),d.length=0)}function r(b){return function(d){h||(h=[b,d],j())}}return b(r(0),r(1)),{
  then:function(b,h){return p((function(r,i){d.push([b,h,r,i]),j()}))}}}a&&(g=m[e]=function(){var b=function(b,d,j,r){function i(i,c){
  h(b,d,j,i,c,r)}r=r||2;var c,u=/Async$/;return u.test(b)?(b=b.replace(u,""),"function"==typeof Promise?new Promise(i):p(i)):h(b,d,j,c,c,r)}
  ;function h(h,d,j,r,i,c){return b._api?b._api(h,d,j,r,i,c):(b.q&&b.q.push([h,d,j,r,i,c]),null)}return b.q=[],b}(),y=function(b){function h(h){
  "function"==typeof h[4]&&h[4](new Error(b))}var d=g.q;if(d){for(var j=0;j<d.length;j++)h(d[j]);d.length=0,d.push=h}},function(){
  (o=n.createElement(t)).async=!0,o.crossOrigin="anonymous",o.src="https://"+l,o.onerror=function(){y("Error loading "+l)}
  ;var b=n.getElementsByTagName(t)[0];b&&b.parentNode?b.parentNode.insertBefore(o,b):n.head.appendChild(o)}(),function(){function b(){}
  function h(b,h,d){g(b,h,d,1)}function d(b,d,j){h("setProperties",{type:b,properties:d},j)}function j(b,h){d("user",b,h)}function r(b,h,d){j({
  uid:b},d),h&&j(h,d)}g.identify=r,g.setUserVars=j,g.identifyAccount=b,g.clearUserCookie=b,g.setVars=d,g.event=function(b,d,j){h("trackEvent",{
  name:b,properties:d},j)},g.anonymize=function(){r(!1)},g.shutdown=function(){h("shutdown")},g.restart=function(){h("restart")},
  g.log=function(b,d){h("log",{level:b,msg:d})},g.consent=function(b){h("setIdentity",{consent:!arguments.length||b})}}(),s="fetch",
  f="XMLHttpRequest",g._w={},g._w[f]=m[f],g._w[s]=m[s],m[s]&&(m[s]=function(){return g._w[s].apply(this,arguments)}),g._v="2.0.0")
  }(window,document,window._fs_namespace,"script",window._fs_script);
    window.dataLayer = window.dataLayer || [];
    function gtag() { dataLayer.push(arguments); }
    gtag('js', new Date());

    gtag('config', 'G-4GRL2M87SZ');
      // Helper to send Google Analytics events safely and log them for debugging
      function trackEvent(eventName, eventParams = {}) {
        try {
          if (typeof gtag === 'function') {
            gtag('event', eventName, eventParams);
            console.log(`[GA Event] ${eventName}:`, eventParams);
          } else {
            console.warn(`[GA Event WARNING] gtag not defined. Tried to track ${eventName}:`, eventParams);
          }
        } catch (err) {
          console.error(`[GA Event ERROR] Failed to track ${eventName}:`, err);
        }
      }

      let viewedIds = [];
      let currentAnimalId = null;
      let conversationHistory = [];
      let factInterval = null;
      let currentDogName = 'this dog';
      let currentDogData = null;
      let activeDogFetchId = 0;

      let userCoords = null;
      function getUserLocation() {
        if (navigator.geolocation) {
          navigator.geolocation.getCurrentPosition(
            (position) => {
              userCoords = {
                lat: position.coords.latitude,
                lon: position.coords.longitude
              };
              console.log('User coordinates loaded:', userCoords);
            },
            (error) => {
              console.warn('Geolocation failed or blocked:', error);
            },
            { timeout: 8000 }
          );
        }
      }

      const CH_CANONICAL_ORIGIN = 'https://chattyhound.com';
      const CH_DEFAULT_OG_IMAGE = CH_CANONICAL_ORIGIN + '/og-image.jpg';

      function getDogIdFromPath(pathname) {
        const match = (pathname || window.location.pathname).match(/^\/dogs\/([^/?#]+)\/?$/);
        return match ? decodeURIComponent(match[1]) : null;
      }

      function getCanonicalDogUrl(animalId) {
        if (!animalId) return CH_CANONICAL_ORIGIN + '/';
        return `${CH_CANONICAL_ORIGIN}/dogs/${encodeURIComponent(animalId)}`;
      }

      function updateDogShareUrl(animalId, replace) {
        if (!animalId) return;
        const target = `/dogs/${encodeURIComponent(animalId)}`;
        const state = { dogId: animalId };
        if (replace) {
          history.replaceState(state, '', target);
        } else {
          history.pushState(state, '', target);
        }
      }

      function pronounForGender(genderStr) {
        const g = (genderStr || '').toLowerCase();
        if (g.includes('female')) return 'her';
        if (g.includes('male')) return 'him';
        return 'them';
      }

      function getDogImageUrl(dog) {
        const d = dog || currentDogData;
        if (d?.image_file && d?.image_base_url) {
          return d.image_base_url + d.image_file;
        }
        if (d?.image_public_url) return d.image_public_url;
        if (d?.image_url) return d.image_url;
        const imgEl = document.getElementById('dogImage');
        if (imgEl?.src) return imgEl.src;
        return CH_DEFAULT_OG_IMAGE;
      }

      async function buildDogShareImageFile(dog) {
        const imageUrl = getDogImageUrl(dog);
        if (!imageUrl || imageUrl === CH_DEFAULT_OG_IMAGE) return null;
        try {
          const res = await fetch(imageUrl);
          if (!res.ok) return null;
          const blob = await res.blob();
          const type = blob.type && blob.type.startsWith('image/') ? blob.type : 'image/jpeg';
          const ext = type.includes('png') ? 'png' : 'jpg';
          const safeName = (dog?.name || currentDogName || 'dog').replace(/[^\w.-]+/g, '-').slice(0, 40);
          return new File([blob], `${safeName}.${ext}`, { type });
        } catch (e) {
          console.warn('Could not load dog image for share:', e);
          return null;
        }
      }

      function buildDogSharePayload(dog) {
        const name = dog?.name || currentDogName || 'this dog';
        const age = cleanAgeText(dog?.age || '');
        const shelter = dog?.located_at || 'Pima Animal Care Center';
        const pron = pronounForGender(dog?.gender);
        const animalId = dog?.animal_id || currentAnimalId;
        const url = getCanonicalDogUrl(animalId);

        let summary = '';
        const facts = dog?.important_facts || [];
        if (facts.length > 0) {
          summary = facts[0];
        } else if (dog?.description || dog?.bio) {
          const snippet = (dog.description || dog.bio).trim().slice(0, 120);
          summary = snippet + ((dog.description || dog.bio).length > 120 ? '…' : '');
        }

        const text = `${name} is an adoptable rescue dog at ${shelter}. Chat with ${pron} and learn more.`;

        return {
          title: `Meet ${name} on ChattyHound 🐶`,
          text,
          url,
          animal_id: animalId,
          dog_name: name
        };
      }

      function updateDocumentMetaForDog(dog) {
        if (!dog || !dog.animal_id) return;
        const name = dog.name || 'this dog';
        const shelter = dog.located_at || 'Pima Animal Care Center';
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

      function updateShareButtonLabels() {
        const label = currentDogName && currentDogName !== 'this dog'
          ? `Share ${currentDogName}`
          : 'Share this dog';
        ['heroShareBtn', 'chatShareBtn'].forEach(id => {
          const btn = document.getElementById(id);
          if (btn) btn.setAttribute('aria-label', label);
        });
      }

      const shareToast = document.getElementById('shareToast');
      let shareToastTimer = null;

      function showShareToast(message) {
        if (!shareToast) return;
        shareToast.textContent = message;
        shareToast.classList.add('visible');
        if (shareToastTimer) clearTimeout(shareToastTimer);
        shareToastTimer = setTimeout(() => {
          shareToast.classList.remove('visible');
        }, 2600);
      }

      const shareFallbackMenu = document.getElementById('shareFallbackMenu');
      let shareFallbackAnchor = null;

      function closeShareFallbackMenu() {
        if (!shareFallbackMenu) return;
        shareFallbackMenu.classList.remove('open');
        shareFallbackMenu.hidden = true;
        shareFallbackMenu.innerHTML = '';
        shareFallbackAnchor = null;
      }

      function openShareFallbackMenu(anchorEl, payload) {
        if (!shareFallbackMenu || !anchorEl) return;
        closeShareFallbackMenu();
        shareFallbackAnchor = anchorEl;

        const items = [
          { id: 'copy', label: 'Copy link', action: () => copyDogShareLink(payload) },
          { id: 'email', label: 'Email', action: () => shareDogByEmail(payload) },
          { id: 'sms', label: 'Text message', action: () => shareDogBySms(payload) }
        ];

        shareFallbackMenu.innerHTML = items.map(item =>
          `<button type="button" role="menuitem" data-share-action="${item.id}">${item.label}</button>`
        ).join('');

        shareFallbackMenu.querySelectorAll('button').forEach((btn, idx) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            items[idx].action();
            closeShareFallbackMenu();
          });
        });

        const rect = anchorEl.getBoundingClientRect();
        shareFallbackMenu.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - 160)}px`;
        shareFallbackMenu.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - 220))}px`;
        shareFallbackMenu.hidden = false;
        shareFallbackMenu.classList.add('open');
        const firstBtn = shareFallbackMenu.querySelector('button');
        if (firstBtn) firstBtn.focus();
      }

      async function copyDogShareLink(payload) {
        const url = payload.url;
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(url);
          } else {
            const ta = document.createElement('textarea');
            ta.value = url;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
          }
          showToast('Dog link copied.');
          trackEvent('dog_share_copied_link', {
            animal_id: payload.animal_id,
            share_method: 'copy_link'
          });
          trackEvent('dog_share_completed', {
            animal_id: payload.animal_id,
            share_method: 'copy_link'
          });
        } catch (err) {
          console.error('Copy failed:', err);
          trackEvent('dog_share_failed', {
            animal_id: payload.animal_id,
            share_method: 'copy_link',
            error: 'clipboard'
          });
          showShareToast('Could not copy link. Please try again.');
        }
      }

      function shareDogByEmail(payload) {
        const subject = encodeURIComponent(payload.title);
        const body = encodeURIComponent(`${payload.text}\n\n${payload.url}`);
        window.location.href = `mailto:?subject=${subject}&body=${body}`;
        trackEvent('dog_share_completed', {
          animal_id: payload.animal_id,
          share_method: 'email'
        });
      }

      function shareDogBySms(payload) {
        const body = encodeURIComponent(`${payload.text} ${payload.url}`);
        const sep = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ? '&' : '?';
        window.location.href = `sms:${sep}body=${body}`;
        trackEvent('dog_share_completed', {
          animal_id: payload.animal_id,
          share_method: 'sms'
        });
      }

      async function shareCurrentDog(anchorEl, dogOverride) {
        const dog = dogOverride || currentDogData;
        if (!dog && !currentAnimalId) return;
        const payload = buildDogSharePayload(dog || { animal_id: currentAnimalId, name: currentDogName });
        trackEvent('dog_share_clicked', {
          animal_id: payload.animal_id,
          share_method: navigator.share ? 'native' : 'fallback'
        });

        if (navigator.share) {
          try {
            const shareData = {
              title: payload.title,
              text: payload.text,
              url: payload.url
            };
            await navigator.share(shareData);
            trackEvent('dog_share_completed', {
              animal_id: payload.animal_id,
              share_method: 'native'
            });
          } catch (err) {
            if (err && err.name === 'AbortError') return;
            console.warn('Native share failed, using fallback:', err);
            openShareFallbackMenu(anchorEl, payload);
          }
        } else {
          openShareFallbackMenu(anchorEl, payload);
        }
      }

      function wireShareButtons() {
        const heroShareBtn = document.getElementById('heroShareBtn');
        const chatShareBtn = document.getElementById('chatShareBtn');
        if (heroShareBtn) {
          heroShareBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            shareCurrentDog(heroShareBtn);
          });
        }
        if (chatShareBtn) {
          chatShareBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            shareCurrentDog(chatShareBtn);
          });
        }
      }

      document.addEventListener('click', (e) => {
        if (shareFallbackMenu && !shareFallbackMenu.hidden && !shareFallbackMenu.contains(e.target) && e.target !== shareFallbackAnchor) {
          closeShareFallbackMenu();
        }
      });
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeShareFallbackMenu();
      });
      wireShareButtons();
      trackEvent('visited_site');

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

      // Setup simple Favorites storage array
      let favoritesList = JSON.parse(localStorage.getItem('chattyhound_favorites') || '[]');

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
      const sendBtn = document.getElementById('sendBtn');

      const favBtn = document.getElementById('favBtn');
      const scrollContent = document.getElementById('scrollContent');

      function stopFactsAnimation() {
        // Stub left for safety/backward compatibility
      }

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

      function cleanAgeText(ageStr) {
        if (!ageStr) return '-';
        let clean = ageStr.replace(/The shelter staff think I am/i, '').replace(/old/i, '').trim();
        clean = clean.replace(/^(?:about|around)\s+/i, '');
        clean = clean.replace(/\byears?\b/gi, 'yr').replace(/\bmonths?\b/gi, 'mo');
        return clean || ageStr;
      }

      function cleanWeightText(weightStr) {
        if (!weightStr) return '-';
        let clean = weightStr.replace(/I weigh approximately/i, '').trim();
        clean = clean.replace(/\bpounds\b/gi, 'lbs');
        
        // Strip decimals and round to nearest whole integer (e.g. "49.00 lbs." -> "49 lbs")
        const numMatch = clean.match(/^(\d+(?:\.\d+)?)\s*(.*)$/);
        if (numMatch) {
          const val = parseFloat(numMatch[1]);
          const unit = numMatch[2].replace(/\./g, '').trim();
          const roundedVal = Math.round(val);
          return `${roundedVal} ${unit || 'lbs'}`.trim();
        }
        
        return clean || weightStr;
      }

      function cleanGenderText(genderStr) {
        if (!genderStr) return '-';
        let clean = genderStr.trim();
        clean = clean.replace(/unaltered/i, 'Unalt.');
        clean = clean.replace(/neutered/i, 'Neut.');
        return clean;
      }

      function showDogUnavailableState(fetchId) {
        setAppState('unavailable');
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
          chatTitleName.textContent = currentDogName;
          const shortLoc = dog.located_at && dog.located_at.includes('Muddy') ? 'MP' : 'PACC';
          dogId.textContent = dog.animal_id ? `${dog.animal_id} • ${shortLoc}` : '';
          if (locationTextEl) {
            locationTextEl.textContent = dog.located_at || 'Pima Animal Care Center';
          }
          const lastCheckedEl = document.getElementById('lastCheckedDate');
          if (lastCheckedEl) {
            lastCheckedEl.textContent = dog.data_updated || 'Today';
          }

          // Populate rotate overlay with current dog details
          const rotateDogPhoto = document.getElementById('rotateDogPhoto');
          const rotateDogTitle = document.getElementById('rotateDogTitle');
          const rotateDogText = document.getElementById('rotateDogText');
          if (rotateDogPhoto) {
            rotateDogPhoto.src = dog.image_public_url || dog.image_url || (dog.image_file ? (dog.image_base_url + dog.image_file) : 'happy_rescue_pup.png');
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
          if (chatInput) chatInput.placeholder = "Ask about " + currentDogName + "...";

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
          if (genderEl) genderEl.textContent = cleanGenderText(dog.gender || 'Unknown');
          dogAge.textContent = cleanAgeText(dog.age || 'Unknown');
          dogWeight.textContent = cleanWeightText(dog.weight || 'Unknown');

          // Restore action overlays on successful load
          if (mobileActionBar) mobileActionBar.style.display = 'flex';
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
          const bioText = (dog.description || dog.bio || '').trim();
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

          if (dog.url) {
            paccLink.href = dog.url;
            paccLink.style.display = 'inline-flex';
          }

          // Update sticky avatar image
          const stickyDogAvatar = document.getElementById('stickyDogAvatar');
          if (stickyDogAvatar) {
            if (dog.image_file && dog.image_base_url) {
              stickyDogAvatar.src = dog.image_base_url + dog.image_file;
            } else if (dog.image_public_url) {
              stickyDogAvatar.src = dog.image_public_url;
            } else if (dog.image_url) {
              stickyDogAvatar.src = dog.image_url;
            } else {
              stickyDogAvatar.src = '';
            }
          }

          // Handle Image
          if (dog.image_file && dog.image_base_url) {
            dogImage.src = dog.image_base_url + dog.image_file;
          } else if (dog.image_public_url) {
            dogImage.src = dog.image_public_url;
          } else if (dog.image_url) {
            dogImage.src = dog.image_url;
          }

          const mobileAdoptBtn = document.getElementById('mobileAdoptBtn');
          if (mobileAdoptBtn && dog.url) {
            mobileAdoptBtn.href = dog.url;
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

      function updateSuggestions(botReplyText) {
        const quickPromptsContainer = document.getElementById('quickPromptsContainer');
        if (!quickPromptsContainer) return;

        const genderEl = document.getElementById('dogGender');
        const dogGender = genderEl ? genderEl.textContent : 'male';
        const pron = (dogGender && dogGender.toLowerCase().includes('female')) ? 'her' : 'him';
        const possessive = pron === 'her' ? 'her' : 'his';

        // Candidate questions mapping
        const candidates = [
          {
            text: `What is your rescue story?`,
            keywords: ['story', 'backstory', 'arrive', 'shelter', 'before', 'past', 'background', 'rescue', 'history'],
            hasAnswer: () => currentDogData && (currentDogData.backstory_summary || currentDogData.bio)
          },
          {
            text: `Are you good with other dogs or cats?`,
            keywords: ['dog', 'cat', 'fren', 'animal', 'pet', 'pack', 'other', 'friend', 'doggy'],
            hasAnswer: () => currentDogData && currentDogData.other_animals_notes
          },
          {
            text: `Are you good with kids or strangers?`,
            keywords: ['kid', 'child', 'family', 'people', 'hooman', 'stranger', 'guest', 'person', 'new', 'introduce'],
            hasAnswer: () => currentDogData && currentDogData.people_notes
          },
          {
            text: `How do you do on walks and leash?`,
            keywords: ['walk', 'leash', 'hike', 'run', 'outside', 'yard', 'fence', 'activity', 'collar', 'pull'],
            hasAnswer: () => currentDogData && currentDogData.containment_notes
          },
          {
            text: `Do you have any medical needs or health concerns?`,
            keywords: ['health', 'medical', 'pill', 'vet', 'treat', 'hurt', 'med', 'injury', 'sick'],
            hasAnswer: () => currentDogData && currentDogData.medical_notes
          },
          {
            text: `What does your ideal home look like?`,
            keywords: ['home', 'house', 'apartment', 'yard', 'live', 'owner', 'family', 'ideal', 'space'],
            hasAnswer: () => currentDogData && (
              (currentDogData.ideal_home && currentDogData.ideal_home.length > 0) || 
              currentDogData.containment_notes
            )
          },
          {
            text: `What are your biggest strengths or best qualities?`,
            keywords: ['good', 'best', 'strength', 'love', 'happy', 'cuddle', 'sweet', 'positives', 'special'],
            hasAnswer: () => currentDogData && currentDogData.strengths && currentDogData.strengths.length > 0
          },
          {
            text: `What quirks or challenges are you working on?`,
            keywords: ['quirk', 'challenge', 'bad', 'difficult', 'scared', 'fear', 'issue', 'work', 'trouble', 'nervous'],
            hasAnswer: () => currentDogData && (
              (currentDogData.challenges && currentDogData.challenges.length > 0) ||
              (currentDogData.risk_flags && currentDogData.risk_flags.length > 0)
            )
          },
          {
            text: `What should my human know?`,
            keywords: ['know', 'human', 'owner', 'adopter', 'tell', 'important', 'advice'],
            hasAnswer: () => true
          },
          {
            text: `What does your perfect day look like?`,
            keywords: ['day', 'perfect', 'routine', 'spend', 'sleep', 'morning', 'night'],
            hasAnswer: () => true
          },
          {
            text: `What are some of your favorite things?`,
            keywords: ['favorite', 'thing', 'toy', 'game', 'play', 'treat', 'food', 'bone', 'snack'],
            hasAnswer: () => true
          }
        ];

        // Filter candidates down to those that have actual answers for this dog
        const answeredCandidates = candidates.filter(c => c.hasAnswer());

        // Get user messages already sent to filter out
        const sentMessages = conversationHistory
          .filter(msg => msg.role === 'user')
          .map(msg => msg.content.toLowerCase().trim());

        let finalPrompts = [];

        if (!botReplyText) {
          // 1. Initial State: show 4 diverse prompts that have answers
          // Prioritize specific questions (where hasAnswer checks a field) over general ones
          const specific = answeredCandidates.filter(c => c.text !== `What should my human know?` && c.text !== `What does your perfect day look like?` && c.text !== `What are some of your favorite things?`);
          const general = answeredCandidates.filter(c => c.text === `What should my human know?` || c.text === `What does your perfect day look like?` || c.text === `What are some of your favorite things?`);
          
          const sortedCandidates = [...specific, ...general];
          
          for (const cand of sortedCandidates) {
            const cleanCand = cand.text.toLowerCase().trim();
            if (!sentMessages.includes(cleanCand)) {
              finalPrompts.push(cand.text);
            }
            if (finalPrompts.length >= 4) break;
          }
        } else {
          // 2. Contextual State: show top 3 prompts based on matching keywords in the conversation context
          const lastUserMsg = conversationHistory.length > 0 ? conversationHistory[conversationHistory.length - 1].content : '';
          const contextText = (botReplyText + ' ' + lastUserMsg).toLowerCase();

          // Find matches
          const matched = answeredCandidates.filter(c => c.keywords.some(kw => contextText.includes(kw)));
          
          // Add matched items first, making sure they haven't been sent yet
          for (const cand of matched) {
            const cleanCand = cand.text.toLowerCase().trim();
            if (!sentMessages.includes(cleanCand) && !finalPrompts.includes(cand.text)) {
              finalPrompts.push(cand.text);
            }
          }

          // If we have fewer than 3 matched items, fill with remaining answered candidates
          if (finalPrompts.length < 3) {
            const specific = answeredCandidates.filter(c => c.text !== `What should my human know?` && c.text !== `What does your perfect day look like?` && c.text !== `What are some of your favorite things?`);
            const general = answeredCandidates.filter(c => c.text === `What should my human know?` || c.text === `What does your perfect day look like?` || c.text === `What are some of your favorite things?`);
            const sortedCandidates = [...specific, ...general];

            for (const cand of sortedCandidates) {
              const cleanCand = cand.text.toLowerCase().trim();
              if (!sentMessages.includes(cleanCand) && !finalPrompts.includes(cand.text)) {
                finalPrompts.push(cand.text);
              }
              if (finalPrompts.length >= 3) break;
            }
          }
          
          // Limit to exactly 3 suggestions for conversational turns
          finalPrompts = finalPrompts.slice(0, 3);
        }

        // Render the suggestions
        quickPromptsContainer.innerHTML = '';
        finalPrompts.forEach(p => {
          const btn = document.createElement('button');
          btn.className = 'prompt-shortcut-btn';
          btn.setAttribute('type', 'button');
          btn.setAttribute('data-prompt', p);
          btn.textContent = p;
          
          const handleImmediateSend = (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (btn.disabled) return;
            const promptText = btn.getAttribute('data-prompt');
            if (promptText && chatInput && !chatInput.disabled) {
              btn.disabled = true;
              btn.style.opacity = '0.6';
              btn.style.background = 'var(--accent)';
              btn.style.color = 'var(--accent-text)';
              trackEvent('suggestion_clicked', { dog_name: currentDogName, prompt_text: promptText });
              sendMessage(promptText);
            }
          };
          btn.addEventListener('click', handleImmediateSend);
          btn.addEventListener('pointerdown', handleImmediateSend);
          
          quickPromptsContainer.appendChild(btn);
        });
      }

      function scrollToBottom() {
        if (scrollContent && window.innerWidth < 800) {
          scrollContent.scrollTop = scrollContent.scrollHeight;
        }
        const profileBody = document.querySelector('.profile-body');
        if (profileBody) {
          profileBody.scrollTop = profileBody.scrollHeight;
        }
      }

      function appendMessage(role, content, avatarLetter = '🐾', shouldScroll = true) {
        const msgRow = document.createElement('div');
        msgRow.className = `msg-row ${role === 'bot' ? 'bot' : 'user'}`;

        if (role === 'bot') {
          const av = document.createElement('div');
          av.className = 'avatar';
          av.textContent = avatarLetter;
          msgRow.appendChild(av);

          const bubble = document.createElement('div');
          bubble.className = 'bubble bot';
          bubble.innerHTML = marked.parse(content);
          msgRow.appendChild(bubble);
        } else {
          const bubble = document.createElement('div');
          bubble.className = 'bubble user';
          bubble.textContent = content;
          msgRow.appendChild(bubble);
        }

        chatHistory.appendChild(msgRow);

        // Smoothly scroll the main layout down as chat history grows
        if (shouldScroll) {
          scrollToBottom();
        }

        // Add to internal history state
        conversationHistory.push({ role: role === 'bot' ? 'assistant' : 'user', content });
      }

      function showTypingIndicator() {
        const container = document.createElement('div');
        container.className = 'msg-row typing-row';
        container.id = 'typingIndicator';

        const av = document.createElement('div');
        av.className = 'avatar';
        av.textContent = currentDogName.charAt(0).toUpperCase();
        container.appendChild(av);

        const bubble = document.createElement('div');
        bubble.className = 'typing-bubble';
        bubble.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
        container.appendChild(bubble);

        chatHistory.appendChild(container);
        scrollToBottom();
      }

      function removeTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
          indicator.remove();
        }
      }

      async function sendMessage(customText = null) {
        if (chatInput.disabled) return; // double-submit safeguard

        const text = (typeof customText === 'string' ? customText : chatInput.value).trim();
        if (!text || !currentAnimalId) return;

        const isFirstMessage = (conversationHistory.length === 0);
        appendMessage('user', text);
        trackEvent('chat_message_sent', { dog_name: currentDogName, message_text: text });
        if (isFirstMessage) {
          trackEvent('first_chat_message_sent', { dog_name: currentDogName });
        }
        chatInput.value = '';
        chatInput.disabled = true;
        sendBtn.disabled = true;

        showTypingIndicator();

        const historyToSend = conversationHistory.slice(0, -1);

        try {
          const currentImageUrl = document.getElementById('dogImage')?.src || '';
          
          let guestSessionId = localStorage.getItem('chattyhound_guest_id');
          if (!guestSessionId) {
            guestSessionId = 'guest_' + Math.random().toString(36).substr(2, 9) + '@guest.chattyhound.com';
            localStorage.setItem('chattyhound_guest_id', guestSessionId);
          }

          const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              animal_id: currentAnimalId,
              message: text,
              conversation_history: historyToSend,
              email: userEmail || guestSessionId,
              dog_name: currentDogName,
              dog_image_url: currentImageUrl
            })
          });

          removeTypingIndicator();

          if (!response.ok) throw new Error('Chat failed');

          const data = await response.json();
          const firstLetter = currentDogName.charAt(0).toUpperCase();
          if (data.reply) {
            appendMessage('bot', data.reply, firstLetter);
            updateSuggestions(data.reply);
          } else {
            appendMessage('bot', '[Error: No reply received]', firstLetter);
          }
        } catch (err) {
          removeTypingIndicator();
          console.error(err);
          appendMessage('bot', '[Sorry, I had trouble responding to that.]', '!');
        } finally {
          chatInput.disabled = false;
          sendBtn.disabled = false;
          chatInput.focus();
        }
      }

      nextBtn.addEventListener('click', () => {
        trackEvent('dog_shuffled');
        const nextDogClicks = parseInt(localStorage.getItem('chattyhound_next_dog_clicks') || '0', 10);
        const hasPromptedLogin = localStorage.getItem('chattyhound_prompted_login');
        if (!userEmail && hasPromptedLogin !== 'true' && nextDogClicks >= 2) {
          localStorage.setItem('chattyhound_prompted_login', 'true');
          window.__CH_INTERRUPTED_NEXT_DOG__ = true;
          openPrefModal();
        } else {
          if (!userEmail) {
            localStorage.setItem('chattyhound_next_dog_clicks', (nextDogClicks + 1).toString());
          }
          fetchRandomDog();
        }
      });
      sendBtn.addEventListener('click', sendMessage);
      chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendMessage();
      });
      // Force viewport scroll reset to fix iOS keyboard layout displacement bug
      chatInput.addEventListener('blur', () => {
        document.body.classList.remove('keyboard-active');
        setTimeout(() => {
          window.scrollTo(0, 0);
        }, 150);
      });
      chatInput.addEventListener('focus', () => {
        enterChatMode();
        document.body.classList.add('keyboard-active');
        setTimeout(() => {
          window.scrollTo(0, 0);
          scrollToBottom();
        }, 150);
      });

      // Dismiss keyboard on outside tap
      document.addEventListener('touchstart', (e) => {
        if (document.body.classList.contains('keyboard-active') && e.target !== chatInput && e.target.closest('.footer-input-bar') === null && e.target.closest('#quickPromptsContainer') === null) {
          chatInput.blur();
        }
      });
      
      const stickyChatBtn = document.getElementById('stickyChatBtn');
      if (stickyChatBtn) {
        stickyChatBtn.addEventListener('click', () => {
          enterChatMode();
          if (chatInput && !chatInput.disabled) {
             chatInput.focus();
          }
        });
      }

      const stickyBackBtn = document.getElementById('stickyBackBtn');
      if (stickyBackBtn) {
        stickyBackBtn.addEventListener('click', () => {
          exitChatMode();
        });
      }

      // Anchor smooth-scrolling ask CTA
      const askBtn = document.getElementById('askBtn');
      if (askBtn) {
        askBtn.addEventListener('click', (e) => {
          e.preventDefault();
          trackEvent('ask_cta_clicked', { dog_name: currentDogName, animal_id: currentAnimalId });
          const chatSec = document.getElementById('chatSection');
          if (chatSec) {
            chatSec.scrollIntoView({ behavior: 'smooth' });
            setTimeout(() => {
              if (chatInput) chatInput.focus();
            }, 400);
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

      let userEmail = localStorage.getItem('chattyhound_user_email') || null;
      let currentPrefs = { gender: 'any', age_group: 'any', size: 'any', location: 'any' };

      // Expanded lifestyle preferences stored locally
      let lifestylePrefs = JSON.parse(localStorage.getItem('chattyhound_lifestyle_prefs') || JSON.stringify({
        energy: 'any',
        home: 'any',
        kids: false,
        dogs: false,
        cats: false,
        shedding: false,
        aloneTime: false,
        training: false
      }));

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
        setTimeout(() => {
          window.scrollTo(0, 0);
          scrollToBottom();
        }, 50);
      }

      function exitChatMode() {
        document.body.classList.remove('chat-engaged');
      }

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
        
        // Defer location prompt until preferences are opened
        if (!userCoords) {
          getUserLocation();
        }

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

      // Landing and Empty state triggers
      const landingStartBtn = document.getElementById('landingStartBtn');
      const landingHowBtn = document.getElementById('landingHowBtn');
      const loginSkipBtn = document.getElementById('loginSkipBtn');

      if (landingStartBtn) {
        landingStartBtn.addEventListener('click', () => {
          trackEvent('start_sniffing_clicked');
          switchView('app');
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
          const nextDogClicks = parseInt(localStorage.getItem('chattyhound_next_dog_clicks') || '0', 10);
          const hasPromptedLogin = localStorage.getItem('chattyhound_prompted_login');
          if (!userEmail && hasPromptedLogin !== 'true' && nextDogClicks >= 2) {
            localStorage.setItem('chattyhound_prompted_login', 'true');
            window.__CH_INTERRUPTED_NEXT_DOG__ = true;
            openPrefModal();
          } else {
            if (!userEmail) {
              localStorage.setItem('chattyhound_next_dog_clicks', (nextDogClicks + 1).toString());
            }
            fetchRandomDog();
          }
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

      function startAppAfterPreferences(loaderFn) {
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
                currentPrefs = {
                  gender: profile.gender || 'any',
                  age_group: profile.age_group || 'any',
                  size: profile.size || 'any',
                  location: profile.location || 'any'
                };
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
      } else if (hasVisited === 'true') {
        switchView('app');
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

      // Sticky Chat button scrolls to chat input
      const stickyChatBtn = document.getElementById('stickyChatBtn');
      if (stickyChatBtn) {
        stickyChatBtn.addEventListener('click', () => {
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

      // ─── SAVED DOGS FEATURE ────────────────────────────────────────────────

      function updateSavedNavBadge() {
        const badge = document.getElementById('savedNavBadge');
        if (!badge) return;
        badge.style.display = favoritesList.length > 0 ? 'block' : 'none';
      }

      async function syncLocalFavoritesToBackend(email) {
        if (!email || favoritesList.length === 0) return;
        try {
          // Fetch existing backend favorites
          const res = await fetch('/api/favorites?email=' + encodeURIComponent(email));
          if (!res.ok) return;
          const data = await res.json();
          const backendIds = (data.saved || []).map(d => d.animal_id);
          // Merge: push any local IDs not yet in backend
          const toSync = favoritesList.filter(id => !backendIds.includes(id));
          // We don't have dog_name/image for stale local IDs, so just upsert with animal_id only
          for (const aid of toSync) {
            await fetch('/api/favorites', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ email, animal_id: aid, action: 'save' })
            });
          }
          // Also merge backend IDs into local list
          let changed = false;
          for (const id of backendIds) {
            if (!favoritesList.includes(id)) {
              favoritesList.push(id);
              changed = true;
            }
          }
          if (changed) localStorage.setItem('chattyhound_favorites', JSON.stringify(favoritesList));
          updateSavedNavBadge();
        } catch (e) {
          console.warn('Favorites sync error:', e);
        }
      }

      // Saved modal state
      let savedActiveTab = 'dogs';

      function openSavedModal() {
        const modal = document.getElementById('savedModal');
        if (!modal) return;
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        loadSavedTab(savedActiveTab);

        // Focus close button inside the modal for accessibility
        const closeBtn = document.getElementById('savedModalCloseBtn');
        if (closeBtn) {
          closeBtn.focus();
        }

        trackEvent('saved_modal_opened');
      }

      function closeSavedModal() {
        const modal = document.getElementById('savedModal');
        if (!modal) return;

        // Remove active element focus if inside the modal to avoid aria-hidden parent focus block warnings
        if (document.activeElement && modal && modal.contains(document.activeElement)) {
          document.activeElement.blur();
        }

        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';

        // Restore focus to the trigger button that opened it
        const savedNavBtn = document.getElementById('savedNavBtn');
        if (savedNavBtn) {
          savedNavBtn.focus();
        }
      }

      async function loadSavedTab(tab) {
        savedActiveTab = tab;
        const content = document.getElementById('savedModalContent');
        if (!content) return;

        // Update tab button styles
        const tabDogs = document.getElementById('savedTabDogs');
        const tabChats = document.getElementById('savedTabChats');
        if (tabDogs && tabChats) {
          if (tab === 'dogs') {
            tabDogs.style.background = 'var(--accent)'; tabDogs.style.color = 'var(--accent-text)';
            tabChats.style.background = 'transparent'; tabChats.style.color = 'var(--text-muted)';
          } else {
            tabChats.style.background = 'var(--teal)'; tabChats.style.color = 'var(--accent-text)';
            tabDogs.style.background = 'transparent'; tabDogs.style.color = 'var(--text-muted)';
          }
        }

        content.innerHTML = '<div style="text-align:center; padding:32px; color:var(--text-muted);"><div style="font-size:2rem;margin-bottom:8px;">🐾</div>Loading...</div>';

        if (tab === 'dogs') {
          await renderSavedDogs(content);
        } else {
          await renderRecentChats(content);
        }
      }

      async function renderSavedDogs(container) {
        // Prefer backend data for logged-in users, fall back to local list
        let dogs = [];
        if (userEmail) {
          try {
            const res = await fetch('/api/favorites?email=' + encodeURIComponent(userEmail));
            if (res.ok) {
              const data = await res.json();
              dogs = data.saved || [];
            }
          } catch (e) { }
        }

        // If no backend data, render from local favoritesList with dynamic detail fetching
        if (dogs.length === 0 && favoritesList.length > 0 && !userEmail) {
          try {
            const promises = favoritesList.map(async (id) => {
              try {
                const res = await fetch(`/api/random_dog?animal_id=${encodeURIComponent(id)}`);
                if (res.ok) {
                  const dog = await res.json();
                  return {
                    animal_id: dog.animal_id,
                    dog_name: dog.name || 'Shelter Pup',
                    gender: dog.gender || 'Unknown',
                    age: dog.age || 'Unknown',
                    weight: dog.weight || 'Unknown',
                    located_at: dog.located_at || 'Pima Animal Care Center',
                    url: dog.url || '',
                    dog_image_url: dog.image_url || dog.image_public_url || ''
                  };
                }
              } catch (e) {}
              return { animal_id: id, dog_name: 'Shelter Pup', dog_image_url: '' };
            });
            dogs = await Promise.all(promises);
          } catch (e) {
            dogs = favoritesList.map(id => ({ animal_id: id, dog_name: 'Shelter Pup', dog_image_url: '' }));
          }
        }

        if (dogs.length === 0) {
          container.innerHTML = `
          <div style="text-align:center; padding:40px 24px;">
            <div style="font-size:3rem; margin-bottom:12px;">💔</div>
            <h3 style="font-size:1.1rem; font-weight:800; color:white; margin-bottom:8px;">No saved dogs yet</h3>
            <p style="font-size:0.85rem; color:var(--text-muted); line-height:1.5; margin-bottom:16px;">Tap the ❤️ on any dog card to save them here and come back later.</p>
            <button class="btn-primary start-sniffing-btn" style="padding:10px 24px; border-radius:9999px; font-size:0.85rem; font-weight:800; cursor:pointer; background:var(--accent); color:var(--accent-text); border:none; box-shadow:0 4px 12px var(--accent-shadow);">Start Sniffing</button>
          </div>`;
          
          container.querySelector('.start-sniffing-btn')?.addEventListener('click', () => {
            closeSavedModal();
            fetchRandomDog();
          });
          return;
        }

        container.innerHTML = dogs.map(d => `
        <div class="saved-dog-card" data-animal-id="${d.animal_id}" style="display:flex; flex-direction:column; gap:12px; padding:16px; border-radius:18px; background:rgba(255,255,255,0.03); margin-bottom:14px; border:1px solid rgba(255,255,255,0.06); position:relative; transition:all 0.2s ease;">
          <!-- Top Row: Photo + Meta + Heart -->
          <div style="display:flex; gap:14px; align-items:flex-start;">
            <div style="width:68px; height:68px; border-radius:12px; overflow:hidden; flex-shrink:0; background:var(--bg-slate-800); border:1px solid rgba(255,255,255,0.1);">
              ${d.dog_image_url ? `<img src="${d.dog_image_url}" alt="${d.dog_name}" style="width:100%;height:100%;object-fit:cover;">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:1.8rem;background:var(--bg-slate-800);">🐾</div>'}
            </div>
            <div style="flex:1; min-width:0; display:flex; flex-direction:column; gap:2px;">
              <h4 style="font-weight:900; font-size:1.1rem; color:white; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin:0;">${d.dog_name || 'Shelter Pup'}</h4>
              <!-- Gender/Age/Weight/Breed mini pills or badges -->
              <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:4px;">
                <span style="font-size:0.68rem; background:rgba(255,255,255,0.05); color:var(--text-muted); padding:2px 6px; border-radius:6px; font-weight:700;">${d.gender || 'Unknown'}</span>
                <span style="font-size:0.68rem; background:rgba(255,255,255,0.05); color:var(--text-muted); padding:2px 6px; border-radius:6px; font-weight:700;">${d.located_at ? (d.located_at.includes('Muddy') ? 'MP' : d.located_at.replace('Pima Animal Care Center', 'PACC')) : 'PACC'}</span>
              </div>
            </div>
            <!-- Right side Action Buttons (Share and Heart toggle) -->
            <div style="display:flex; flex-direction:column; gap:8px; align-items:flex-end;">
              <button type="button" class="modal-unheart-btn" data-animal-id="${d.animal_id}" aria-label="Remove ${d.dog_name || 'dog'} from My Dogs" style="background:transparent; border:none; color:var(--accent); font-size:1.25rem; cursor:pointer; padding:4px; display:flex; align-items:center; justify-content:center; transition:transform 0.2s;">
                ❤️
              </button>
              <button type="button" class="share-btn compact saved-card-share-btn" data-animal-id="${d.animal_id}" data-location="${d.located_at || 'Pima Animal Care Center'}" data-dog-name="${(d.dog_name || 'Shelter Pup').replace(/"/g, '&quot;')}" aria-label="Share ${d.dog_name || 'this dog'}" title="Share" style="width:28px; height:28px;">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:block;"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
              </button>
            </div>
          </div>
          <!-- Bottom Row: Twin CTA Buttons -->
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:4px;">
            <button type="button" class="modal-chat-cta" data-animal-id="${d.animal_id}" style="padding:8px; border:1px solid var(--accent); border-radius:10px; background:var(--accent); color:var(--accent-text); font-weight:800; font-size:0.78rem; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px; transition:all 0.2s ease;">
              Chat 💬
            </button>
            <a href="${d.url || 'https://www.pima.gov/pacc'}" target="_blank" rel="noopener noreferrer" class="modal-shelter-link" style="text-decoration:none; padding:8px; border:1px solid rgba(255,255,255,0.12); border-radius:10px; background:rgba(255,255,255,0.04); color:var(--text-main); font-weight:800; font-size:0.78rem; display:flex; align-items:center; justify-content:center; gap:4px; transition:all 0.2s ease;">
              Shelter Page 🔗
            </a>
          </div>
        </div>`).join('');

        container.querySelectorAll('.saved-card-share-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const aid = btn.getAttribute('data-animal-id');
            const name = btn.getAttribute('data-dog-name');
            const loc = btn.getAttribute('data-location') || 'Pima Animal Care Center';
            shareCurrentDog(btn, { animal_id: aid, name, located_at: loc });
          });
        });

        // unheart inside the modal
        container.querySelectorAll('.modal-unheart-btn').forEach(btn => {
          btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const aid = btn.getAttribute('data-animal-id');
            const targetDog = dogs.find(dg => dg.animal_id === aid);
            const name = targetDog ? targetDog.dog_name : 'Shelter Pup';

            // Remove from favorite list
            const index = favoritesList.indexOf(aid);
            if (index > -1) {
              favoritesList.splice(index, 1);
              localStorage.setItem('chattyhound_favorites', JSON.stringify(favoritesList));
              updateSavedNavBadge();
            }

            // Sync active dog heart if it is currently displaying this dog
            if (currentAnimalId === aid && favBtn) {
              favBtn.classList.remove('favorited');
              favBtn.setAttribute('aria-label', `Save ${currentDogName} to My Dogs`);
            }

            showToast("Removed from My Dogs.");

            // Hot-reload list
            loadSavedTab('dogs');

            // Sync to backend if logged in
            if (userEmail) {
              try {
                await fetch('/api/favorites', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    email: userEmail,
                    animal_id: aid,
                    action: 'remove'
                  })
                });
              } catch (err) {
                console.warn('Backend favorites sync failed:', err);
              }
            }
          });
        });

        // Click Chat CTA
        container.querySelectorAll('.modal-chat-cta').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const aid = btn.getAttribute('data-animal-id');
            closeSavedModal();
            fetchSpecificDog(aid);
          });
        });

        // Click card generally
        container.querySelectorAll('.saved-dog-card').forEach(card => {
          card.addEventListener('click', (e) => {
            if (e.target.closest('button') || e.target.closest('a') || e.target.closest('.modal-unheart-btn')) return;
            const aid = card.getAttribute('data-animal-id');
            closeSavedModal();
            fetchSpecificDog(aid);
          });
        });
      }

      async function renderRecentChats(container) {
        if (!userEmail) {
          container.innerHTML = `
          <div style="text-align:center; padding:40px 24px;">
            <div style="font-size:3rem; margin-bottom:12px;">🔒</div>
            <h3 style="font-size:1.1rem; font-weight:800; color:white; margin-bottom:8px;">Sign in to see chats</h3>
            <p style="font-size:0.85rem; color:var(--text-muted); line-height:1.5;">Your chat history is saved when you're signed in. Sign in to pick up where you left off!</p>
            <button class="btn-primary" onclick="closeSavedModal();setTimeout(openPrefModal,200);" style="margin-top:16px; padding:10px 24px; border-radius:9999px; font-size:0.85rem; font-weight:800; cursor:pointer;">Sign In</button>
          </div>`;
          return;
        }

        try {
          const res = await fetch('/api/chat_history?email=' + encodeURIComponent(userEmail));
          if (!res.ok) throw new Error('Failed');
          const data = await res.json();
          const convs = data.conversations || [];

          if (convs.length === 0) {
            container.innerHTML = `
            <div style="text-align:center; padding:40px 24px;">
              <div style="font-size:3rem; margin-bottom:12px;">💬</div>
              <h3 style="font-size:1.1rem; font-weight:800; color:white; margin-bottom:8px;">No chats yet</h3>
              <p style="font-size:0.85rem; color:var(--text-muted); line-height:1.5; margin-bottom:16px;">Start chatting with any dog to build your conversation history here.</p>
              <button class="btn-primary meet-dogs-btn" style="padding:10px 24px; border-radius:9999px; font-size:0.85rem; font-weight:800; cursor:pointer; background:var(--teal); color:var(--accent-text); border:none; box-shadow:0 4px 12px rgba(20,184,166,0.25);">Meet dogs</button>
            </div>`;
            
            container.querySelector('.meet-dogs-btn')?.addEventListener('click', () => {
              closeSavedModal();
            });
            return;
          }

          container.innerHTML = convs.map(c => {
            const dateStr = c.updated_at ? new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
            return `
          <div class="saved-dog-card" data-animal-id="${c.animal_id}" style="display:flex; align-items:center; gap:12px; padding:12px; border-radius:14px; background:rgba(255,255,255,0.03); margin-bottom:10px; cursor:pointer; transition:all 0.2s ease; border:1px solid rgba(255,255,255,0.06);">
            <div style="width:52px; height:52px; border-radius:10px; overflow:hidden; flex-shrink:0; background:var(--bg-slate-800); border:1px solid rgba(255,255,255,0.08);">
              ${c.dog_image_url ? `<img src="${c.dog_image_url}" alt="${c.dog_name}" style="width:100%;height:100%;object-fit:cover;">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:1.5rem;background:var(--bg-slate-800);">💬</div>'}
            </div>
            <div style="flex:1; min-width:0;">
              <div style="font-weight:800; font-size:0.95rem; color:white; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${c.dog_name || 'Shelter Pup'}</div>
              <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${c.last_message_preview || 'Tap to continue'}</div>
            </div>
            <button type="button" class="share-btn compact saved-card-share-btn" data-animal-id="${c.animal_id}" data-dog-name="${(c.dog_name || 'Shelter Pup').replace(/"/g, '&quot;')}" aria-label="Share ${(c.dog_name || 'this dog').replace(/"/g, '')}" title="Share" style="width:28px; height:28px;">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:block;"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
            </button>
            <div style="font-size:0.7rem; color:var(--text-muted); white-space:nowrap; margin-left:4px;">${dateStr}</div>
          </div>`;
          }).join('');

          container.querySelectorAll('.saved-dog-card').forEach(card => {
            card.addEventListener('click', (e) => {
              if (e.target.closest('.saved-card-share-btn')) return;
              const aid = card.getAttribute('data-animal-id');
              closeSavedModal();
              fetchSpecificDog(aid, true);
            });
          });

          container.querySelectorAll('.saved-card-share-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
              e.stopPropagation();
              const aid = btn.getAttribute('data-animal-id');
              const name = btn.getAttribute('data-dog-name');
              const loc = btn.getAttribute('data-location') || 'Pima Animal Care Center';
              shareCurrentDog(btn, { animal_id: aid, name, located_at: loc });
            });
          });

        } catch (e) {
          container.innerHTML = `<div style="text-align:center;padding:24px;color:var(--text-muted);">Unable to load chats. Please try again.</div>`;
        }
      }

      async function fetchSpecificDog(animalId, resumeChat = false) {
        switchView('app');
        localStorage.setItem('chattyhound_visited', 'true');
        if (scrollContent) scrollContent.scrollTop = 0;
        await fetchRandomDog(animalId, { resumeChat });
      }

      async function openSharedDogFromRoute(animalId) {
        switchView('app');
        localStorage.setItem('chattyhound_visited', 'true');
        await fetchRandomDog(animalId, { replaceUrl: true });
      }

      // Saved Modal event wiring
      const savedNavBtn = document.getElementById('savedNavBtn');
      const savedModalCloseBtn = document.getElementById('savedModalCloseBtn');
      const savedTabDogs = document.getElementById('savedTabDogs');
      const savedTabChats = document.getElementById('savedTabChats');
      const savedModal = document.getElementById('savedModal');

      if (savedNavBtn) {
        savedNavBtn.addEventListener('click', openSavedModal);
      }
      if (savedModalCloseBtn) {
        savedModalCloseBtn.addEventListener('click', closeSavedModal);
      }
      if (savedModal) {
        savedModal.addEventListener('click', (e) => {
          if (e.target === savedModal) closeSavedModal();
        });
      }
      if (savedTabDogs) {
        savedTabDogs.addEventListener('click', () => loadSavedTab('dogs'));
      }
      if (savedTabChats) {
        savedTabChats.addEventListener('click', () => loadSavedTab('chats'));
      }

      // On init: show Saved button if user is logged in, update badge
      if (userEmail && savedNavBtn) {
        savedNavBtn.style.display = '';
      }
      updateSavedNavBadge();

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

