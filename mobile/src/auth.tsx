import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, ApiError, Preferences, SavedDog } from './api';

const KEYS = {
  email: 'chattyhound_user_email',
  prefs: 'chattyhound_prefs',
  favorites: 'chattyhound_favorites',
  visited: 'chattyhound_visited',
} as const;

const DEFAULT_PREFS: Preferences = {
  gender: 'any',
  age_group: 'any',
  size: 'any',
  location: 'any',
};

/** Minimal dog record cached locally so My Dogs works for guests + offline. */
export interface FavoriteDog {
  animal_id: string;
  dog_name: string;
  dog_image_url?: string;
  shelter_name?: string;
  shelter_profile_url?: string;
  age?: string;
  gender?: string;
  weight?: string;
}

interface AuthState {
  ready: boolean;
  email: string | null;
  preferences: Preferences;
  favorites: Record<string, FavoriteDog>;
  visited: boolean;
}

interface AuthContextValue extends AuthState {
  isLoggedIn: boolean;
  login: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  deleteAccount: () => Promise<void>;
  savePreferences: (partial: Partial<Preferences>) => Promise<void>;
  isFavorite: (animalId: string) => boolean;
  toggleFavorite: (dog: FavoriteDog) => Promise<boolean>; // returns new saved state
  refreshFavorites: () => Promise<void>;
  markVisited: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    ready: false,
    email: null,
    preferences: DEFAULT_PREFS,
    favorites: {},
    visited: false,
  });

  // ---- bootstrap from storage, then best-effort server refresh ----
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [email, prefsRaw, favRaw, visited] = await Promise.all([
        AsyncStorage.getItem(KEYS.email),
        AsyncStorage.getItem(KEYS.prefs),
        AsyncStorage.getItem(KEYS.favorites),
        AsyncStorage.getItem(KEYS.visited),
      ]);

      let preferences = DEFAULT_PREFS;
      if (prefsRaw) {
        try {
          preferences = { ...DEFAULT_PREFS, ...JSON.parse(prefsRaw) };
        } catch {}
      }
      let favorites: Record<string, FavoriteDog> = {};
      if (favRaw) {
        try {
          favorites = JSON.parse(favRaw) || {};
        } catch {}
      }

      if (cancelled) return;
      setState({
        ready: true,
        email: email || null,
        preferences,
        favorites,
        visited: visited === 'true',
      });

      // Server refresh if logged in (non-blocking).
      if (email) {
        try {
          const profile = await api.login(email);
          if (!cancelled) {
            const next = { ...DEFAULT_PREFS, ...profile };
            setState((s) => ({ ...s, preferences: next }));
            AsyncStorage.setItem(KEYS.prefs, JSON.stringify(next));
          }
        } catch {}
        try {
          const { saved } = await api.favorites(email);
          if (!cancelled && saved) {
            setState((s) => ({ ...s, favorites: mergeFavorites(s.favorites, saved) }));
          }
        } catch {}
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const persistFavorites = useCallback((favs: Record<string, FavoriteDog>) => {
    AsyncStorage.setItem(KEYS.favorites, JSON.stringify(favs)).catch(() => {});
  }, []);

  const login = useCallback(async (rawEmail: string) => {
    const email = rawEmail.trim().toLowerCase();
    if (!email) throw new ApiError('Email is required.', 400);
    const profile = await api.login(email);
    const preferences = { ...DEFAULT_PREFS, ...profile };
    await AsyncStorage.multiSet([
      [KEYS.email, email],
      [KEYS.prefs, JSON.stringify(preferences)],
    ]);
    setState((s) => ({ ...s, email, preferences }));
    // Pull server favorites in the background.
    try {
      const { saved } = await api.favorites(email);
      if (saved) {
        setState((s) => {
          const merged = mergeFavorites(s.favorites, saved);
          persistFavorites(merged);
          return { ...s, favorites: merged };
        });
      }
    } catch {}
  }, [persistFavorites]);

  const signOut = useCallback(async () => {
    await AsyncStorage.multiRemove([KEYS.email, KEYS.prefs]);
    setState((s) => ({ ...s, email: null, preferences: DEFAULT_PREFS }));
  }, []);

  /**
   * Permanently delete the user's data (Apple Guideline 5.1.1). Deletes
   * server-side data when signed in, then wipes all local state either way.
   */
  const deleteAccount = useCallback(async () => {
    const email = state.email;
    if (email) {
      await api.deleteAccount(email); // throws on failure so the UI can report it
    }
    await AsyncStorage.multiRemove([KEYS.email, KEYS.prefs, KEYS.favorites]);
    setState((s) => ({
      ...s,
      email: null,
      preferences: DEFAULT_PREFS,
      favorites: {},
    }));
  }, [state.email]);

  const savePreferences = useCallback(
    async (partial: Partial<Preferences>) => {
      // Compute next prefs from the current snapshot (deps keep this fresh) so
      // the value is available synchronously for the API call below.
      const nextPrefs: Preferences = { ...state.preferences, ...partial };
      setState((s) => ({ ...s, preferences: { ...s.preferences, ...partial } }));
      AsyncStorage.setItem(KEYS.prefs, JSON.stringify(nextPrefs)).catch(() => {});
      const email = state.email;
      if (email) {
        try {
          const res = await api.savePreferences({
            email,
            gender: nextPrefs.gender,
            age_group: nextPrefs.age_group,
            size: nextPrefs.size,
            location: nextPrefs.location,
          });
          if (res?.preferences) {
            const merged = { ...DEFAULT_PREFS, ...res.preferences };
            setState((s) => ({ ...s, preferences: merged }));
            AsyncStorage.setItem(KEYS.prefs, JSON.stringify(merged)).catch(() => {});
          }
        } catch {}
      }
    },
    [state.email, state.preferences]
  );

  const isFavorite = useCallback(
    (animalId: string) => Boolean(state.favorites[animalId]),
    [state.favorites]
  );

  const toggleFavorite = useCallback(
    async (dog: FavoriteDog): Promise<boolean> => {
      const currentlySaved = Boolean(state.favorites[dog.animal_id]);
      const nextSaved = !currentlySaved;

      // Optimistic local update.
      setState((s) => {
        const favs = { ...s.favorites };
        if (nextSaved) favs[dog.animal_id] = dog;
        else delete favs[dog.animal_id];
        persistFavorites(favs);
        return { ...s, favorites: favs };
      });

      // Sync to server when logged in.
      const email = state.email;
      if (email) {
        try {
          await api.setFavorite({
            email,
            animal_id: dog.animal_id,
            action: nextSaved ? 'save' : 'remove',
            dog_name: dog.dog_name,
            dog_image_url: dog.dog_image_url,
          });
        } catch {
          // ignore — local state is the source of truth for UI
        }
      }
      return nextSaved;
    },
    [state.email, state.favorites, persistFavorites]
  );

  const refreshFavorites = useCallback(async () => {
    const email = state.email;
    if (!email) return;
    try {
      const { saved } = await api.favorites(email);
      if (saved) {
        setState((s) => {
          const merged = mergeFavorites(s.favorites, saved);
          persistFavorites(merged);
          return { ...s, favorites: merged };
        });
      }
    } catch {}
  }, [state.email, persistFavorites]);

  const markVisited = useCallback(() => {
    setState((s) => (s.visited ? s : { ...s, visited: true }));
    AsyncStorage.setItem(KEYS.visited, 'true').catch(() => {});
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      isLoggedIn: Boolean(state.email),
      login,
      signOut,
      deleteAccount,
      savePreferences,
      isFavorite,
      toggleFavorite,
      refreshFavorites,
      markVisited,
    }),
    [
      state,
      login,
      signOut,
      deleteAccount,
      savePreferences,
      isFavorite,
      toggleFavorite,
      refreshFavorites,
      markVisited,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}

function mergeFavorites(
  local: Record<string, FavoriteDog>,
  serverSaved: SavedDog[]
): Record<string, FavoriteDog> {
  const merged: Record<string, FavoriteDog> = { ...local };
  for (const s of serverSaved) {
    merged[s.animal_id] = {
      animal_id: s.animal_id,
      dog_name: s.dog_name,
      dog_image_url: s.dog_image_url,
      shelter_name: s.shelter_name,
      shelter_profile_url: s.shelter_profile_url,
      age: s.age,
      gender: s.gender,
      weight: s.weight,
    };
  }
  return merged;
}
