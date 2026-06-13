/**
 * ChattyHound design tokens, ported from the live site's CSS custom properties.
 * Keep these in sync with public/index.html :root variables.
 */

export const colors = {
  // Backgrounds
  slate950: '#0f172a',
  slate900: '#182235',
  slate800: '#202c44',
  slate700: '#334155',
  bgDeep: '#020617', // radial gradient endpoint

  // Accent (warm amber / gold)
  accent: '#f59e0b',
  accentHover: '#fbbf24',
  accentText: '#111827',
  accentShadow: 'rgba(245, 158, 11, 0.25)',

  // Teal / emerald (match badge + positive states)
  teal: '#14b8a6',
  tealBg: 'rgba(20, 184, 166, 0.08)',
  tealBorder: 'rgba(20, 184, 166, 0.2)',

  // Amber tints (warning / potential match)
  amber: '#f59e0b',
  amberBg: 'rgba(245, 158, 11, 0.06)',
  amberBorder: 'rgba(245, 158, 11, 0.2)',

  // Cream highlight (favorite button bg)
  cream: '#fff7ed',
  creamBg: 'rgba(254, 243, 199, 0.08)',

  // Text
  textMain: '#f8fafc',
  textMuted: '#cbd5e1',
  textFaint: '#94a3b8',
  textOnBubble: '#f1f5f9',

  // Borders & surfaces
  borderSoft: 'rgba(255, 255, 255, 0.08)',
  surfaceFaint: 'rgba(255, 255, 255, 0.02)',
  surface: 'rgba(255, 255, 255, 0.05)',
  chipBorder: 'rgba(255, 255, 255, 0.12)',

  // Status
  danger: '#ef4444',
  white: '#ffffff',
} as const;

export const radius = {
  sm: 12,
  md: 16,
  lg: 18,
  xl: 20,
  pill: 9999,
  bubble: 20,
} as const;

export const spacing = {
  xs: 6,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
} as const;

export const font = {
  // Loaded via @expo-google-fonts/inter in app/_layout.tsx
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  extrabold: 'Inter_800ExtraBold',
  black: 'Inter_900Black',
} as const;

export const shadow = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.4,
    shadowRadius: 24,
    elevation: 8,
  },
  accent: {
    shadowColor: colors.accent,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 14,
    elevation: 6,
  },
} as const;
