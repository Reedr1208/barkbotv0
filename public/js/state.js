// ─── Global State Variables ─────────────────────────────────────────────────
// These are the shared mutable state that all other modules reference.

let viewedIds = [];
let currentAnimalId = null;
let conversationHistory = [];
let factInterval = null;
let currentDogName = 'this dog';
let currentDogData = null;
let activeDogFetchId = 0;

let userCoords = null;

// Kick off browser geolocation ONLY on local dev as a fallback.
// Production relies on Vercel geo-IP headers — never prompt real users.
const _isLocalDev = ['localhost', '127.0.0.1'].includes(location.hostname);
const _geoCoordsPromise = new Promise((resolve) => {
  if (!_isLocalDev || !navigator.geolocation) return resolve(null);
  const timeout = setTimeout(() => resolve(null), 3000);
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      clearTimeout(timeout);
      resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude });
    },
    () => { clearTimeout(timeout); resolve(null); },
    { timeout: 3000, maximumAge: 300000 }
  );
});

window.__CH_LOCATIONS_DATA__ = [];

const CH_CANONICAL_ORIGIN = 'https://chattyhound.com';
const CH_DEFAULT_OG_IMAGE = CH_CANONICAL_ORIGIN + '/chattyhound_og.png';

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

// Setup simple Favorites storage array
let favoritesList = JSON.parse(localStorage.getItem('chattyhound_favorites') || '[]');

// Saved modal tab state
let savedActiveTab = 'dogs';

// ─── Suggestion System State ────────────────────────────────────────────────
// Cached from /api/suggested_prompts (fetched once, persisted across dogs)
let suggestedPromptsCache = null; // { informative: [...], whimsical: [...] }

// Per-dog suggestion state (reset on each new dog)
let suggestionState = {
  pools: { informative: [], whimsical: [], profile: [] },
  usedPrompts: new Set(),
  current: {
    informative: { text: null, turnsShown: 0 },
    whimsical:   { text: null, turnsShown: 0 },
    profile:     { text: null, turnsShown: 0 },
  },
};

// The 3 suggestions currently displayed to the user (populated by updateSuggestions)
let activeSuggestions = [];
