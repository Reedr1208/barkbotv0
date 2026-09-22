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
