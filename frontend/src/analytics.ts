import { Platform } from 'react-native';
import { posthog } from './posthog';

/**
 * Tracks custom analytics events.
 * Safe to call on all platforms:
 * - On Web: calls gtag() and FS.event() if loaded.
 * - On Mobile: writes logs to console for debugging.
 */
export function trackEvent(eventName: string, eventParams: Record<string, any> = {}) {
  // Capture event in PostHog if initialized
  if (posthog) {
    try {
      posthog.capture(eventName, eventParams);
    } catch (err) {
      console.error(`[PostHog Event ERROR] Failed to track ${eventName}:`, err);
    }
  }

  if (Platform.OS === 'web') {
    try {
      const globalAny = global as any;
      if (typeof globalAny.gtag === 'function') {
        globalAny.gtag('event', eventName, eventParams);
        console.log(`[GA Event] ${eventName}:`, eventParams);
      } else {
        console.warn(`[GA Event WARNING] gtag not defined. Tried to track ${eventName}:`, eventParams);
      }
      if (typeof globalAny.FS?.event === 'function') {
        globalAny.FS.event(eventName, eventParams);
        console.log(`[FS Event] ${eventName}:`, eventParams);
      }
    } catch (err) {
      console.error(`[GA Event ERROR] Failed to track ${eventName}:`, err);
    }
  } else {
    // Log to console on native mobile devices for debugging
    console.log(`[Mobile Log Event] ${eventName}:`, eventParams);
  }
}

