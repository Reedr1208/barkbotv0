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
