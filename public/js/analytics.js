// ─── Analytics ──────────────────────────────────────────────────────────────
// Helper to send Google Analytics events safely and log them for debugging

// Auto-detected context injected into every event
const _isMobile = /Mobi|Android/i.test(navigator.userAgent);
const _isTablet = /iPad|Android(?!.*Mobi)/i.test(navigator.userAgent);
const _deviceType = _isTablet ? 'tablet' : (_isMobile ? 'mobile' : 'desktop');

function trackEvent(eventName, eventParams = {}) {
  try {
    // Auto-inject device type and user region into every event
    const enriched = {
      device_type: _deviceType,
      ...eventParams
    };
    // Attach detected region if available (set by location detection)
    if (window.__CH_DETECTED_CITY__) {
      enriched.user_region = window.__CH_DETECTED_CITY__;
    }
    if (typeof gtag === 'function') {
      gtag('event', eventName, enriched);
      console.log(`[GA Event] ${eventName}:`, enriched);
    } else {
      console.warn(`[GA Event WARNING] gtag not defined. Tried to track ${eventName}:`, enriched);
    }
  } catch (err) {
    console.error(`[GA Event ERROR] Failed to track ${eventName}:`, err);
  }
}

// ─── Google Ads Conversion Tracking ─────────────────────────────────────────

/**
 * Fire the primary Google Ads conversion: user's first chat message to a dog.
 * Also reports the matching OpenAI (ChatGPT) Ads conversion.
 */
function trackAdsFirstMessage() {
  trackOpenAIAdsConversion('first_chat_message_sent');
  if (typeof gtag !== 'function') return;
  gtag('event', 'conversion', {
    'send_to': 'AW-18221330739/hZRVCIfIrYQdELPizfBD'
  });
  console.log('[Google Ads] Conversion fired: chat_first_message');
}

/**
 * Fire the secondary Google Ads conversion: clicking the shelter listing link.
 * Also reports the matching OpenAI (ChatGPT) Ads conversion.
 */
function trackAdsShelterClick() {
  trackOpenAIAdsConversion('shelter_link_clicked');
  if (typeof gtag !== 'function') return;
  gtag('event', 'conversion', {
    'send_to': 'AW-18221330739/x_EcCIrIrYQdELPizfBD'
  });
  console.log('[Google Ads] Conversion fired: shelter_listing_click');
}

// ─── OpenAI (ChatGPT) Ads Conversion Tracking ──────────────────────────────

// Persist the ChatGPT ad click reference (?oppref=...) from the landing URL so
// server-side conversions can still be attributed after in-app navigation.
(function captureOppref() {
  try {
    const ref = new URLSearchParams(window.location.search).get('oppref');
    if (ref) localStorage.setItem('chattyhound_oppref', ref);
  } catch (e) { /* storage unavailable */ }
})();

function _getOppref() {
  try {
    const stored = localStorage.getItem('chattyhound_oppref');
    if (stored) return stored;
  } catch (e) { /* storage unavailable */ }
  const m = document.cookie.match(/(?:^|;\s*)__oppref=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

/**
 * Report a conversion to OpenAI Ads via both the browser pixel and our
 * server-side Conversions API relay. Both share one event_id so OpenAI
 * deduplicates them into a single conversion.
 */
function trackOpenAIAdsConversion(eventName) {
  const eventId = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
  try {
    if (typeof oaiq === 'function') {
      oaiq('measure', 'custom', { type: 'custom' }, { custom_event_name: eventName, event_id: eventId });
      console.log(`[OpenAI Ads] Pixel conversion fired: ${eventName}`);
    }
  } catch (err) {
    console.error('[OpenAI Ads] Pixel error:', err);
  }
  try {
    const payload = JSON.stringify({
      event_name: eventName,
      event_id: eventId,
      source_url: window.location.href,
      oppref: _getOppref()
    });
    // sendBeacon survives navigation (e.g. shelter link clicks); fall back to keepalive fetch
    const sent = navigator.sendBeacon &&
      navigator.sendBeacon('/api/ads/conversion', new Blob([payload], { type: 'application/json' }));
    if (!sent) {
      fetch('/api/ads/conversion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true
      }).catch(() => {});
    }
  } catch (err) {
    console.error('[OpenAI Ads] Server relay error:', err);
  }
}
