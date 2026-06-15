// ─── Saved Dogs Feature ─────────────────────────────────────────────────────
// Favorites, saved dogs modal, recent chats, and backend sync

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
// savedActiveTab is declared in state.js

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
              located_at: dog.shelter_name || 'Pima Animal Care Center',
              url: dog.shelter_profile_url || '',
              dog_image_url: dog.shelter_image_url || ''
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
          <span style="font-size:0.68rem; background:rgba(255,255,255,0.05); color:var(--text-muted); padding:2px 6px; border-radius:6px; font-weight:700;">${d.shelter_name ? (d.shelter_name.includes('PAWS') ? 'PAWSCH' : (d.shelter_name.includes('Muddy') ? 'MP' : (d.shelter_name.includes('Humane') || d.shelter_name.includes('HSSA') ? 'HSSA' : (d.shelter_name.includes('Animal Care Centers') || d.shelter_name.includes('NYC') ? 'NYCACC' : d.shelter_name.replace('Pima Animal Care Center', 'PACC'))))) : 'PACC'}</span>
        </div>
      </div>
      <!-- Right side Action Buttons (Share and Heart toggle) -->
      <div style="display:flex; flex-direction:column; gap:8px; align-items:flex-end;">
        <button type="button" class="modal-unheart-btn" data-animal-id="${d.animal_id}" aria-label="Remove ${d.dog_name || 'dog'} from My Dogs" style="background:transparent; border:none; color:var(--accent); font-size:1.25rem; cursor:pointer; padding:4px; display:flex; align-items:center; justify-content:center; transition:transform 0.2s;">
          ❤️
        </button>
        <button type="button" class="share-btn compact saved-card-share-btn" data-animal-id="${d.animal_id}" data-location="${d.shelter_name || 'Pima Animal Care Center'}" data-dog-name="${(d.dog_name || 'Shelter Pup').replace(/"/g, '&quot;')}" aria-label="Share ${d.dog_name || 'this dog'}" title="Share" style="width:28px; height:28px;">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:block;"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
        </button>
      </div>
    </div>
    <!-- Bottom Row: Twin CTA Buttons -->
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:4px;">
      <button type="button" class="modal-chat-cta" data-animal-id="${d.animal_id}" style="padding:8px; border:1px solid var(--accent); border-radius:10px; background:var(--accent); color:var(--accent-text); font-weight:800; font-size:0.78rem; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px; transition:all 0.2s ease;">
        Chat 💬
      </button>
      <a href="${d.shelter_profile_url || 'https://www.pima.gov/pacc'}" target="_blank" rel="noopener noreferrer" class="modal-shelter-link" style="text-decoration:none; padding:8px; border:1px solid rgba(255,255,255,0.12); border-radius:10px; background:rgba(255,255,255,0.04); color:var(--text-main); font-weight:800; font-size:0.78rem; display:flex; align-items:center; justify-content:center; gap:4px; transition:all 0.2s ease;">
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
      shareCurrentDog(btn, { animal_id: aid, name, shelter_name: loc });
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
        shareCurrentDog(btn, { animal_id: aid, name, shelter_name: loc });
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
