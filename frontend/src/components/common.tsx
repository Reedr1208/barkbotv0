import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, font, spacing } from '../theme';
import { Button, Pill } from './ui';

export function EmptyState({
  icon = '🐾',
  title,
  description,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: {
  icon?: string;
  title: string;
  description?: string;
  primaryLabel?: string;
  onPrimary?: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
}) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyIcon}>{icon}</Text>
      <Text style={styles.emptyTitle}>{title}</Text>
      {!!description && <Text style={styles.emptyDesc}>{description}</Text>}
      <View style={styles.emptyActions}>
        {primaryLabel && onPrimary && (
          <Button label={primaryLabel} onPress={onPrimary} style={styles.emptyBtn} />
        )}
        {secondaryLabel && onSecondary && (
          <Button
            label={secondaryLabel}
            variant="secondary"
            onPress={onSecondary}
            style={styles.emptyBtn}
          />
        )}
      </View>
    </View>
  );
}

export interface Option<T extends string> {
  label: string;
  value: T;
}

/** A labelled row of selectable pills (single-select). */
export function SegmentedField<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.fieldOptions}>
        {options.map((opt) => (
          <Pill
            key={opt.value}
            label={opt.label}
            active={value === opt.value}
            onPress={() => onChange(opt.value)}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: {
    alignItems: 'center',
    paddingVertical: 48,
    paddingHorizontal: spacing.xl,
  },
  emptyIcon: { fontSize: 48, marginBottom: spacing.md },
  emptyTitle: {
    fontFamily: font.black,
    fontSize: 19,
    color: colors.textMain,
    textAlign: 'center',
    marginBottom: 8,
  },
  emptyDesc: {
    fontFamily: font.regular,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textMuted,
    textAlign: 'center',
    maxWidth: 320,
  },
  emptyActions: { marginTop: spacing.xl, gap: spacing.sm, alignSelf: 'stretch' },
  emptyBtn: { alignSelf: 'stretch' },
  field: { marginBottom: spacing.lg },
  fieldLabel: {
    fontFamily: font.extrabold,
    fontSize: 12.5,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    color: colors.textFaint,
    marginBottom: spacing.sm,
  },
  fieldOptions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
});
