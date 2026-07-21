/**
 * Typed client for the ChattyHound Vercel API.
 * Field shapes mirror the Python endpoints in /api of the web repo.
 */
import Constants from 'expo-constants';

import { Platform } from 'react-native';

const extra = (Constants.expoConfig?.extra ?? {}) as {
  apiBaseUrl?: string;
  siteUrl?: string;
};

export const API_BASE_URL = Platform.OS === 'web' ? '' : (extra.apiBaseUrl ?? 'https://chattyhound.com');
export const SITE_URL = extra.siteUrl ?? 'https://chattyhound.com';

/** Anonymous identity the backend recognizes when no real email is present. */
export const ANON_EMAIL = 'anonymous@chattyhound.com';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Gender = 'any' | 'male' | 'female';
export type AgeGroup = 'any' | 'puppy' | 'young' | 'adult' | 'senior';
export type Size = 'any' | 'small' | 'medium' | 'large';

export interface Preferences {
  email?: string;
  gender: Gender;
  age_group: AgeGroup;
  size: Size;
  location: string; // display name or 'any'
  updated_at?: string;
}

export interface MatchDetail {
  active: boolean;
  preferred: string;
  actual: string;
  matched: boolean;
}

export interface MatchDetails {
  gender?: MatchDetail;
  age?: MatchDetail;
  size?: MatchDetail;
  location?: MatchDetail;
}

/** Full dog object returned by /api/random_dog (and used everywhere). */
export interface Dog {
  animal_id: string;
  name: string;
  gender?: string;
  age?: string;
  age_summary?: string;
  weight?: string;
  weight_summary?: string;
  age_bucket?: string;
  weight_class?: string;
  sex?: string;
  altered_status?: string;
  bio?: string;
  description?: string;
  url?: string;
  located_at?: string;
  more_info?: string;
  shelter_name?: string;
  shelter_url?: string;
  shelter_image_url?: string;
  image_file?: string;
  image_public_url?: string;
  image_base_url?: string;
  intro_summary?: string;
  important_facts?: string[];
  risk_flags?: string[];
  strengths?: string[];
  challenges?: string[];
  ideal_home?: string[];
  other_animals_notes?: string;
  people_notes?: string;
  containment_notes?: string;
  medical_notes?: string;
  adoption_process_notes?: string;
  unknowns?: string[];
  info_refreshed_at?: string;
  preferences_matched?: boolean;
  user_has_preferences?: boolean;
  match_details?: MatchDetails;
  suggested_location?: string;
}

export interface SavedDog {
  animal_id: string;
  dog_name: string;
  gender?: string;
  age?: string;
  weight?: string;
  shelter_name?: string;
  shelter_profile_url?: string;
  dog_image_url?: string;
  created_at?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
}

export interface ConversationSummary {
  animal_id: string;
  dog_name: string;
  dog_image_url?: string;
  last_message_preview?: string;
  updated_at?: string;
}

export interface LocationOption {
  display_name: string;
  relative_path: string;
  shelter_ids: string[];
}

// ---------------------------------------------------------------------------
// Core fetch helper
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: 'GET' | 'POST'; body?: unknown; signal?: AbortSignal } = {}
): Promise<T> {
  const { method = 'GET', body, signal } = options;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (e) {
    throw new ApiError('Network request failed. Check your connection.', 0);
  }

  const text = await res.text();
  let data: any = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const message = (data && data.error) || `Request failed (${res.status}).`;
    throw new ApiError(message, res.status);
  }
  return data as T;
}

function qs(params: Record<string, string | undefined | null>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') {
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    }
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  /** POST /api/login — frictionless email login; returns the prefs profile. */
  login(email: string) {
    return request<Preferences & { id?: number }>('/api/login', {
      method: 'POST',
      body: { email },
    });
  },

  /** GET /api/locations */
  locations() {
    return request<{ locations: LocationOption[] }>('/api/locations');
  },

  /** POST /api/save_preferences */
  savePreferences(prefs: {
    email: string;
    gender?: Gender;
    age_group?: AgeGroup;
    size?: Size;
    location?: string;
  }) {
    return request<{ ok: boolean; preferences: Preferences }>('/api/save_preferences', {
      method: 'POST',
      body: prefs,
    });
  },

  /**
   * GET /api/random_dog — a preference-matched dog, or a specific one via animal_id.
   * `viewed` is a comma-separated list of already-seen animal_ids.
   */
  randomDog(params: {
    email?: string;
    viewed?: string[];
    animal_id?: string;
    gender?: Gender;
    age_group?: AgeGroup;
    size?: Size;
    location?: string;
    signal?: AbortSignal;
  }) {
    const { signal, viewed, ...rest } = params;
    const query = qs({
      ...rest,
      viewed: viewed && viewed.length ? viewed.join(',') : undefined,
    });
    return request<Dog>(`/api/random_dog${query}`, { signal });
  },

  /** POST /api/chat */
  chat(body: {
    animal_id: string;
    message: string;
    conversation_history: ChatMessage[];
    email?: string;
    dog_name?: string;
    dog_image_url?: string;
    signal?: AbortSignal;
  }) {
    const { signal, ...rest } = body;
    return request<{ reply: string }>('/api/chat', { method: 'POST', body: rest, signal });
  },

  /** GET /api/chat_history?email=&animal_id= — messages for one dog. */
  chatMessages(email: string, animal_id: string) {
    return request<{ conversation_id: number | null; messages: ChatMessage[] }>(
      `/api/chat_history${qs({ email, animal_id })}`
    );
  },

  /** GET /api/chat_history?email= — recent conversations list. */
  conversations(email: string) {
    return request<{ conversations: ConversationSummary[] }>(
      `/api/chat_history${qs({ email })}`
    );
  },

  /** GET /api/favorites?email= */
  favorites(email: string) {
    return request<{ saved: SavedDog[] }>(`/api/favorites${qs({ email })}`);
  },

  /** POST /api/delete_account — permanently delete all data for an email. */
  deleteAccount(email: string) {
    return request<{ status: 'deleted' }>('/api/delete_account', {
      method: 'POST',
      body: { email },
    });
  },

  /** POST /api/favorites — save or remove. */
  setFavorite(body: {
    email: string;
    animal_id: string;
    action: 'save' | 'remove';
    dog_name?: string;
    dog_image_url?: string;
  }) {
    return request<{ status: 'saved' | 'removed' }>('/api/favorites', {
      method: 'POST',
      body,
    });
  },
};
