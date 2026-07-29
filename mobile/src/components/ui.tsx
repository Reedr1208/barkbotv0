import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { colors, font, radius, spacing } from '../theme';

/** A bordered surface card used for grouped content sections. */
export function Card({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: ViewStyle | ViewStyle[];
}) {
  return <View style={[styles.card, style]}>{children}</View>;
}

/** Small uppercase section label ("⚡ QUICK FACTS"). */
export function SectionLabel({ children }: { children: React.ReactNode }) {
  return <Text style={styles.sectionLabel}>{children}</Text>;
}

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'teal' | 'danger';

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  style,
  textStyle,
}: {
  label: string;
  onPress?: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle | ViewStyle[];
  textStyle?: TextStyle;
}) {
  const v = VARIANTS[variant];
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        v.container,
        (disabled || loading) && styles.buttonDisabled,
        pressed && !disabled && styles.buttonPressed,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={v.text.color as string} />
      ) : (
        <Text style={[styles.buttonText, v.text, textStyle]}>{label}</Text>
      )}
    </Pressable>
  );
}

/** Pill chip used for traits and selectable options. */
export function Pill({
  label,
  active,
  onPress,
  style,
}: {
  label: string;
  active?: boolean;
  onPress?: () => void;
  style?: ViewStyle;
}) {
  const content = <Text style={[styles.pillText, active && styles.pillTextActive]}>{label}</Text>;
  const base = [styles.pill, active && styles.pillActive, style];

  if (!onPress) {
    return <View style={base}>{content}</View>;
  }
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!active }}
      style={({ pressed }) => [...base, pressed && styles.pillPressed]}
    >
      {content}
    </Pressable>
  );
}

const VARIANTS: Record<ButtonVariant, { container: ViewStyle; text: TextStyle }> = {
  primary: {
    container: { backgroundColor: colors.accent },
    text: { color: colors.accentText },
  },
  secondary: {
    container: {
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderColor: colors.borderSoft,
    },
    text: { color: colors.textMain },
  },
  ghost: {
    container: { backgroundColor: 'transparent' },
    text: { color: colors.textMuted },
  },
  teal: {
    container: { backgroundColor: colors.teal },
    text: { color: '#04201d' },
  },
  danger: {
    container: {
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderColor: 'rgba(239, 68, 68, 0.5)',
    },
    text: { color: colors.danger },
  },
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceFaint,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radius.xl,
    padding: spacing.lg,
  },
  sectionLabel: {
    fontFamily: font.black,
    fontSize: 12,
    letterSpacing: 1,
    textTransform: 'uppercase',
    color: colors.textMuted,
    marginBottom: spacing.sm,
  },
  button: {
    minHeight: 48,
    borderRadius: radius.pill,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
  },
  buttonText: {
    fontFamily: font.extrabold,
    fontSize: 15,
  },
  buttonDisabled: { opacity: 0.5 },
  buttonPressed: { opacity: 0.85, transform: [{ scale: 0.98 }] },
  pill: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(15, 23, 42, 0.5)',
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  pillActive: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  pillPressed: { opacity: 0.8 },
  pillText: {
    fontFamily: font.bold,
    fontSize: 13,
    color: '#e2e8f0',
  },
  pillTextActive: { color: colors.accentText },
});
