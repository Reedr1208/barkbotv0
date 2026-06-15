// ─── Analytics ──────────────────────────────────────────────────────────────
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
