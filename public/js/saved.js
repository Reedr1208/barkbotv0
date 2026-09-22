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
  // Fetch from backend (always available now via device email)
  let dogs = [];
  try {
    const res = await fetch('/api/favorites?email=' + encodeURIComponent(userEmail));
    if (res.ok) {
      const data = await res.json();
      dogs = data.saved || [];
    }
  } catch (e) { }

  // Merge in any localStorage-only favorites not yet in backend
  const backendIds = new Set(dogs.map(d => d.animal_id));
  const localOnly = favoritesList.filter(id => !backendIds.has(id));

  if (localOnly.length > 0) {
    const localDogs = await Promise.all(localOnly.map(async (id) => {
      try {
        const res = await fetch(`/api/random_dog?animal_id=${encodeURIComponent(id)}`);
        if (res.ok) {
          const dog = await res.json();
          // Sync to backend (non-blocking)
          fetch('/api/favorites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: userEmail, animal_id: id, dog_name: dog.name || '', dog_image_url: dog.shelter_image_url || '', action: 'save' })
          }).catch(() => {});
          return {
            animal_id: dog.animal_id,
            dog_name: dog.name || 'Shelter Pup',
            gender: dog.gender || '',
            age: dog.age || '',
            age_summary: dog.age_summary || '',
            weight: dog.weight || '',
            breed_or_description: dog.breed_or_description || '',
            shelter_name: dog.shelter_name || '',
            shelter_profile_url: dog.shelter_profile_url || '',
            city: dog.city || '',
            state: dog.state || '',
            relative_path: dog.relative_path || '',
            dog_image_url: dog.shelter_image_url || ''
          };
        }
      } catch (e) {}
      return { animal_id: id, dog_name: 'Shelter Pup', dog_image_url: '' };
    }));
    dogs = dogs.concat(localDogs);
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

  // Build cards HTML with 2-per-row grid on desktop, 1 on mobile
  const cardsHtml = dogs.map(d => {
    const breed = d.breed_or_description || '';
    const age = d.age_summary || d.age || '';
    const shelterName = d.shelter_name || '';
    const location = (d.city && d.state) ? `${d.city}, ${d.state}` : (d.city || d.state || '');
    const shelterUrl = d.shelter_profile_url || '';
    const relativePath = d.relative_path || '';
    // Build subtitle line: breed · age (skip empty parts)
    const subtitleParts = [breed, age].filter(Boolean);
    const subtitle = subtitleParts.join(' · ');
    // Build location line: shelter name — city, state
    const locationParts = [shelterName, location].filter(Boolean);
    const locationLine = locationParts.join(' — ');

    return `
    <div class="saved-dog-card" data-animal-id="${d.animal_id}" style="display:flex; flex-direction:column; gap:10px; padding:14px; border-radius:16px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); position:relative; transition:all 0.2s ease; cursor:pointer;">
      <!-- Top Row: Photo + Meta + Heart -->
      <div style="display:flex; gap:10px; align-items:flex-start;">
        <div style="width:56px; height:56px; border-radius:10px; overflow:hidden; flex-shrink:0; background:var(--bg-slate-800); border:1px solid rgba(255,255,255,0.1);">
          ${d.dog_image_url ? `<img src="${d.dog_image_url}" alt="${d.dog_name}" style="width:100%;height:100%;object-fit:cover;">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:1.5rem;background:var(--bg-slate-800);">🐾</div>'}
        </div>
        <div style="flex:1; min-width:0; display:flex; flex-direction:column; gap:2px;">
          <h4 style="font-weight:900; font-size:1rem; color:white; margin:0; word-wrap:break-word;">${d.dog_name || 'Shelter Pup'}</h4>
          ${breed ? `<div style="font-size:0.75rem; color:var(--text-muted); font-weight:600; line-height:1.3; word-wrap:break-word;">${breed}</div>` : ''}
          ${age ? `<div style="font-size:0.72rem; color:var(--text-muted); font-weight:500; line-height:1.3;">${age}</div>` : ''}
          ${locationLine ? `<div style="font-size:0.68rem; color:var(--text-muted); line-height:1.3; word-wrap:break-word;">📍 ${locationLine}</div>` : ''}
        </div>
        <!-- Heart + Share -->
        <div style="display:flex; flex-direction:column; gap:6px; align-items:flex-end; flex-shrink:0;">
          <button type="button" class="modal-unheart-btn" data-animal-id="${d.animal_id}" aria-label="Remove ${d.dog_name || 'dog'} from My Dogs" style="background:transparent; border:none; color:var(--accent); font-size:1.1rem; cursor:pointer; padding:2px; display:flex; align-items:center; justify-content:center; transition:transform 0.2s;">
            ❤️
          </button>
          <button type="button" class="share-btn compact saved-card-share-btn" data-animal-id="${d.animal_id}" data-location="${shelterName}" data-relative-path="${relativePath}" data-dog-name="${(d.dog_name || 'Shelter Pup').replace(/"/g, '&quot;')}" aria-label="Share ${d.dog_name || 'this dog'}" title="Share" style="width:24px; height:24px;">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:block;"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
          </button>
        </div>
      </div>
      <!-- CTA Buttons (stacked vertically) -->
      <div style="display:flex; flex-direction:column; gap:6px;">
        <button type="button" class="modal-chat-cta" data-animal-id="${d.animal_id}" style="padding:7px; border:1px solid var(--accent); border-radius:8px; background:var(--accent); color:var(--accent-text); font-weight:800; font-size:0.75rem; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px; transition:all 0.2s ease;">
          Chat 💬
        </button>
        ${shelterUrl
          ? `<a href="${shelterUrl}" target="_blank" rel="noopener noreferrer" class="modal-shelter-link" style="text-decoration:none; padding:7px; border:1px solid rgba(255,255,255,0.12); border-radius:8px; background:rgba(255,255,255,0.04); color:var(--text-main); font-weight:800; font-size:0.75rem; display:flex; align-items:center; justify-content:center; gap:4px; transition:all 0.2s ease;">
              Shelter Page 🔗
            </a>`
          : ''}
      </div>
    </div>`;
  }).join('');

  const isDesktop = window.matchMedia('(min-width: 1024px)').matches;
  const gridCols = isDesktop ? 'repeat(2, 1fr)' : '1fr';
  container.innerHTML = `<div class="saved-dogs-grid" style="display:grid; grid-template-columns:${gridCols}; gap:14px;">${cardsHtml}</div>`;

  container.querySelectorAll('.saved-card-share-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const aid = btn.getAttribute('data-animal-id');
      const name = btn.getAttribute('data-dog-name');
      const loc = btn.getAttribute('data-location') || '';
      const relPath = btn.getAttribute('data-relative-path') || '';
      shareCurrentDog(btn, { animal_id: aid, name, shelter_name: loc, relative_path: relPath });
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
  try {
    const res = await fetch('/api/chat_history?email=' + encodeURIComponent(userEmail));
    if (!res.ok) throw new Error('Failed');
    const data = await res.json();
    const convs = data.conversations || [];
    const chatRetention = data.chat_retention !== false; // default true

    // ── Header with controls ──
    const headerHtml = `
    <div style="display:flex; flex-direction:column; gap:10px; margin-bottom:14px;">
      <!-- Never retain toggle -->
      <div style="display:flex; align-items:center; justify-content:space-between; padding:10px 14px; border-radius:12px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);">
        <div style="display:flex; flex-direction:column; gap:2px;">
          <span style="font-size:0.82rem; font-weight:700; color:white;">Save chat history</span>
          <span style="font-size:0.7rem; color:var(--text-muted);">Resume conversations where you left off</span>
        </div>
        <label class="retention-toggle" style="position:relative; display:inline-block; width:44px; height:24px; flex-shrink:0; cursor:pointer;">
          <input type="checkbox" id="chatRetentionToggle" ${chatRetention ? 'checked' : ''} style="opacity:0; width:0; height:0;">
          <span style="position:absolute; top:0; left:0; right:0; bottom:0; background:${chatRetention ? 'var(--teal)' : 'rgba(255,255,255,0.15)'}; border-radius:24px; transition:0.3s; display:block;">
            <span style="position:absolute; content:''; height:18px; width:18px; left:${chatRetention ? '22px' : '3px'}; bottom:3px; background:white; border-radius:50%; transition:0.3s; display:block; box-shadow:0 1px 3px rgba(0,0,0,0.3);"></span>
          </span>
        </label>
      </div>
      ${convs.length > 0 ? `
      <!-- Delete all button -->
      <button type="button" id="deleteAllChatsBtn" style="display:flex; align-items:center; justify-content:center; gap:6px; padding:8px; border-radius:10px; background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.15); color:#ef4444; font-size:0.78rem; font-weight:700; cursor:pointer; transition:all 0.2s;">
        🗑️ Delete all conversations
      </button>` : ''}
    </div>`;

    if (convs.length === 0) {
      container.innerHTML = headerHtml + `
      <div style="text-align:center; padding:32px 24px;">
        <div style="font-size:3rem; margin-bottom:12px;">💬</div>
        <h3 style="font-size:1.1rem; font-weight:800; color:white; margin-bottom:8px;">No chats yet</h3>
        <p style="font-size:0.85rem; color:var(--text-muted); line-height:1.5; margin-bottom:16px;">${chatRetention ? 'Start chatting with any dog to build your conversation history here.' : 'Chat history is turned off. Enable it above to save your conversations.'}</p>
        <button class="btn-primary meet-dogs-btn" style="padding:10px 24px; border-radius:9999px; font-size:0.85rem; font-weight:800; cursor:pointer; background:var(--teal); color:var(--accent-text); border:none; box-shadow:0 4px 12px rgba(20,184,166,0.25);">Meet dogs</button>
      </div>`;

      _wireRetentionToggle(container);
      container.querySelector('.meet-dogs-btn')?.addEventListener('click', () => {
        closeSavedModal();
      });
      return;
    }

    const convsHtml = convs.map(c => {
      const dateStr = c.updated_at ? new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
      const available = c.is_available !== false;
      const unavailBadge = available ? '' : '<span style="font-size:0.65rem; background:rgba(251,191,36,0.15); color:#fbbf24; padding:2px 6px; border-radius:6px; font-weight:700; white-space:nowrap;">Adopted 🎉</span>';
      const opacity = available ? '1' : '0.6';
      const cursorStyle = available ? 'cursor:pointer;' : 'cursor:default;';
      return `
    <div class="saved-dog-card ${available ? '' : 'unavailable'}" data-animal-id="${c.animal_id}" data-available="${available}" style="display:flex; align-items:center; gap:12px; padding:12px; border-radius:14px; background:rgba(255,255,255,0.03); margin-bottom:10px; ${cursorStyle} transition:all 0.2s ease; border:1px solid rgba(255,255,255,0.06); opacity:${opacity}; position:relative;">
      <div style="width:52px; height:52px; border-radius:10px; overflow:hidden; flex-shrink:0; background:var(--bg-slate-800); border:1px solid rgba(255,255,255,0.08);">
        ${c.dog_image_url ? `<img src="${c.dog_image_url}" alt="${c.dog_name}" style="width:100%;height:100%;object-fit:cover;${available ? '' : 'filter:grayscale(40%);'}">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:1.5rem;background:var(--bg-slate-800);">💬</div>'}
      </div>
      <div style="flex:1; min-width:0;">
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="font-weight:800; font-size:0.95rem; color:white; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${c.dog_name || 'Shelter Pup'}</span>
          ${unavailBadge}
        </div>
        <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${available ? (c.last_message_preview || 'Tap to continue') : 'No longer available for chat'}</div>
      </div>
      <!-- Delete conversation button -->
      <button type="button" class="delete-chat-btn" data-animal-id="${c.animal_id}" data-dog-name="${(c.dog_name || 'Shelter Pup').replace(/"/g, '&quot;')}" aria-label="Delete chat with ${(c.dog_name || 'this dog').replace(/"/g, '')}" title="Delete chat" style="width:28px; height:28px; display:flex; align-items:center; justify-content:center; background:transparent; border:1px solid rgba(239,68,68,0.2); border-radius:8px; color:rgba(239,68,68,0.6); font-size:0.75rem; cursor:pointer; flex-shrink:0; transition:all 0.2s;">
        ✕
      </button>
      <div style="font-size:0.7rem; color:var(--text-muted); white-space:nowrap; margin-left:0px;">${dateStr}</div>
    </div>`;
    }).join('');

    container.innerHTML = headerHtml + convsHtml;

    // ── Wire retention toggle ──
    _wireRetentionToggle(container);

    // ── Wire delete all ──
    const deleteAllBtn = container.querySelector('#deleteAllChatsBtn');
    if (deleteAllBtn) {
      deleteAllBtn.addEventListener('click', async () => {
        if (!confirm('Delete all chat history? This cannot be undone.')) return;
        deleteAllBtn.disabled = true;
        deleteAllBtn.textContent = 'Deleting...';
        try {
          await fetch('/api/chat_history', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: userEmail })
          });
          showToast('All chats deleted.');
          loadSavedTab('chats');
        } catch (e) {
          showToast('Failed to delete. Try again.');
          deleteAllBtn.disabled = false;
          deleteAllBtn.textContent = '🗑️ Delete all conversations';
        }
      });
    }

    // ── Wire individual delete buttons ──
    container.querySelectorAll('.delete-chat-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const aid = btn.getAttribute('data-animal-id');
        const dogName = btn.getAttribute('data-dog-name');
        if (!confirm(`Delete your chat with ${dogName}?`)) return;
        btn.disabled = true;
        btn.textContent = '…';
        try {
          await fetch('/api/chat_history', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: userEmail, animal_id: aid })
          });
          // Remove the card with animation
          const card = btn.closest('.saved-dog-card');
          if (card) {
            card.style.transition = 'all 0.3s ease';
            card.style.opacity = '0';
            card.style.transform = 'translateX(40px)';
            setTimeout(() => {
              card.remove();
              // If no cards left, reload tab
              if (!container.querySelector('.saved-dog-card')) loadSavedTab('chats');
            }, 300);
          }
          showToast(`Chat with ${dogName} deleted.`);
        } catch (e) {
          showToast('Failed to delete. Try again.');
          btn.disabled = false;
          btn.textContent = '✕';
        }
      });
    });

    // ── Wire conversation resume clicks ──
    container.querySelectorAll('.saved-dog-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.delete-chat-btn') || e.target.closest('.saved-card-share-btn')) return;
        const aid = card.getAttribute('data-animal-id');
        const available = card.getAttribute('data-available') !== 'false';
        if (!available) {
          const toast = document.createElement('div');
          toast.textContent = 'This dog has been adopted or is no longer available 🎉';
          toast.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.85);color:white;padding:10px 20px;border-radius:12px;font-size:0.82rem;font-weight:600;z-index:10001;animation:fadeIn 0.2s ease;';
          document.body.appendChild(toast);
          setTimeout(() => toast.remove(), 3000);
          return;
        }
        closeSavedModal();
        fetchSpecificDog(aid, true);
      });
    });

  } catch (e) {
    container.innerHTML = `<div style="text-align:center;padding:24px;color:var(--text-muted);">Unable to load chats. Please try again.</div>`;
  }
}


function _wireRetentionToggle(container) {
  const toggle = container.querySelector('#chatRetentionToggle');
  if (!toggle) return;

  toggle.addEventListener('change', async () => {
    const retain = toggle.checked;
    const slider = toggle.nextElementSibling;
    const knob = slider?.querySelector('span');

    // Immediate visual update
    slider.style.background = retain ? 'var(--teal)' : 'rgba(255,255,255,0.15)';
    if (knob) knob.style.left = retain ? '22px' : '3px';

    if (!retain) {
      if (!confirm('Turn off chat history? This will delete all your existing conversations and stop saving new ones.')) {
        // Revert
        toggle.checked = true;
        slider.style.background = 'var(--teal)';
        if (knob) knob.style.left = '22px';
        return;
      }
    }

    try {
      await fetch('/api/chat_retention', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: userEmail, retain })
      });
      showToast(retain ? 'Chat history enabled.' : 'Chat history disabled — existing chats deleted.');
      loadSavedTab('chats');
    } catch (e) {
      showToast('Failed to update. Try again.');
      // Revert toggle
      toggle.checked = !retain;
      slider.style.background = !retain ? 'var(--teal)' : 'rgba(255,255,255,0.15)';
      if (knob) knob.style.left = !retain ? '22px' : '3px';
    }
  });
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

// Always show My Dogs tab (no auth gate)
if (savedNavBtn) {
  savedNavBtn.style.display = '';
}
updateSavedNavBadge();
