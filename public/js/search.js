// ─── Dog Search ─────────────────────────────────────────────────────
// Client-side search: loads eligible dogs once, filters as user types

let _searchDogsCache = null;
let _searchLoading = false;

async function loadSearchDogs() {
  if (_searchDogsCache) return _searchDogsCache;
  if (_searchLoading) return null;
  _searchLoading = true;
  try {
    const res = await fetch('/api/search_dogs');
    if (!res.ok) throw new Error('Failed to load search data');
    const data = await res.json();
    _searchDogsCache = data.dogs || [];
    return _searchDogsCache;
  } catch (e) {
    console.error('Search dogs load error:', e);
    return [];
  } finally {
    _searchLoading = false;
  }
}

function openSearchOverlay() {
  const overlay = document.getElementById('searchOverlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  overlay.setAttribute('aria-hidden', 'false');
  const input = document.getElementById('searchInput');
  if (input) {
    input.value = '';
    input.focus();
  }
  document.getElementById('searchResults').innerHTML = '';
  document.getElementById('searchStatus').textContent = 'Type a name to search...';
  // Load data in background
  loadSearchDogs();
  document.body.style.overflow = 'hidden';
}

function closeSearchOverlay() {
  const overlay = document.getElementById('searchOverlay');
  if (!overlay) return;
  overlay.style.display = 'none';
  overlay.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

let _searchDebounce = null;

function handleSearchInput(e) {
  const query = (e.target.value || '').trim().toLowerCase();
  clearTimeout(_searchDebounce);
  
  if (!query) {
    document.getElementById('searchResults').innerHTML = '';
    document.getElementById('searchStatus').textContent = 'Type a name to search...';
    return;
  }

  _searchDebounce = setTimeout(async () => {
    const dogs = await loadSearchDogs();
    if (!dogs || !dogs.length) {
      document.getElementById('searchStatus').textContent = 'Loading...';
      return;
    }

    const matches = dogs.filter(d => d.name.toLowerCase().includes(query));
    const resultsEl = document.getElementById('searchResults');
    const statusEl = document.getElementById('searchStatus');

    if (!matches.length) {
      resultsEl.innerHTML = '';
      statusEl.textContent = `No hounds found matching "${e.target.value.trim()}"`;
      return;
    }

    // Show max 20 results
    const shown = matches.slice(0, 20);
    statusEl.textContent = matches.length > 20 
      ? `Showing 20 of ${matches.length} matches`
      : `${matches.length} match${matches.length !== 1 ? 'es' : ''} found`;

    resultsEl.innerHTML = shown.map(dog => `
      <button class="search-result-item" data-animal-id="${dog.id}" onclick="selectSearchDog('${dog.id}')">
        <img class="search-result-avatar" src="${dog.image_url}" alt="${dog.name}" 
             onerror="this.src='happy_rescue_pup.png'" loading="lazy" />
        <div class="search-result-info">
          <span class="search-result-name">${escapeHtml(dog.name)}</span>
          <span class="search-result-meta">${escapeHtml(dog.city)}${dog.state ? ', ' + dog.state : ''} · ${dog.shelter_id}</span>
        </div>
      </button>
    `).join('');
  }, 150);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function selectSearchDog(animalId) {
  closeSearchOverlay();
  if (typeof fetchRandomDog === 'function') {
    fetchRandomDog(animalId);
  }
}

// Wire up events after DOM ready
document.addEventListener('DOMContentLoaded', () => {
  const searchBtn = document.getElementById('searchBtn');
  if (searchBtn) searchBtn.addEventListener('click', openSearchOverlay);

  const searchClose = document.getElementById('searchCloseBtn');
  if (searchClose) searchClose.addEventListener('click', closeSearchOverlay);

  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.addEventListener('input', handleSearchInput);

  // Close on overlay background click
  const overlay = document.getElementById('searchOverlay');
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeSearchOverlay();
    });
  }

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSearchOverlay();
  });
});
