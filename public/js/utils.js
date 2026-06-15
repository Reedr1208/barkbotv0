// ─── Utility Functions ──────────────────────────────────────────────────────
// Pure functions with no DOM side effects (except getDogImageUrl which reads DOM as fallback)

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

function formatRelativeTime(isoString) {
  if (!isoString) return 'Today';
  const updated = new Date(isoString);
  const now = new Date();
  const diffMs = now - updated;
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) {
    return diffDays === 1 ? '1 day ago' : `${diffDays} days ago`;
  } else if (diffHours > 0) {
    return diffHours === 1 ? '1 hour ago' : `${diffHours} hours ago`;
  } else {
    return 'Just now';
  }
}

function pronounForGender(genderStr) {
  const g = (genderStr || '').toLowerCase();
  if (g.includes('female')) return 'her';
  if (g.includes('male')) return 'him';
  return 'them';
}

function getDogIdFromPath(pathname) {
  const path = pathname || window.location.pathname;
  const matchWithLoc = path.match(/^\/dogs\/[^/]+\/([^/?#]+)\/?$/);
  if (matchWithLoc) return decodeURIComponent(matchWithLoc[1]);
  const match = path.match(/^\/dogs\/([^/?#]+)\/?$/);
  if (match) {
    const val = decodeURIComponent(match[1]);
    if (window.__CH_INITIAL_LOCATION__ === '/' + val) return null;
    return val;
  }
  return null;
}

function getCanonicalDogUrl(animalId) {
  const sel = document.getElementById('headerLocationSelect');
  let locPath = sel && sel.value !== 'any' ? sel.value : '';
  if (locPath === 'all') locPath = '/alldogs';
  if (!animalId) return CH_CANONICAL_ORIGIN + '/';
  return `${CH_CANONICAL_ORIGIN}/dogs${locPath}/${encodeURIComponent(animalId)}`;
}

function updateDogShareUrl(animalId, replace) {
  if (!animalId) return;
  const sel = document.getElementById('headerLocationSelect');
  let locPath = sel && sel.value !== 'any' ? sel.value : '';
  if (locPath === 'all') locPath = '/alldogs';
  const target = `/dogs${locPath}/${encodeURIComponent(animalId)}`;
  const state = { dogId: animalId, locationPath: locPath };
  if (replace) {
    history.replaceState(state, '', target);
  } else {
    history.pushState(state, '', target);
  }
}

function getDogImageUrl(dog) {
  const d = dog || currentDogData;
  if (d?.image_file && d?.image_base_url) {
    return d.image_base_url + d.image_file;
  }
  if (d?.shelter_image_url) return d.shelter_image_url;
  if (d?.shelter_image_url) return d.shelter_image_url;
  const imgEl = document.getElementById('dogImage');
  if (imgEl?.src) return imgEl.src;
  return CH_DEFAULT_OG_IMAGE;
}
