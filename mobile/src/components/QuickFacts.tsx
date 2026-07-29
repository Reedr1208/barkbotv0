import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Dog } from '../api';
import { colors, font, radius } from '../theme';
import { dogAge, dogSex, dogWeight } from '../utils';

type MatchState = 'match' | 'mismatch' | 'neutral';

function FactChip({
  label,
  value,
  state,
}: {
  label: string;
  value: string;
  state: MatchState;
}) {
  const matched = state === 'match';
  const mismatched = state === 'mismatch';
  return (
    <View
      style={[
        styles.chip,
        matched && styles.chipMatch,
        mismatched && styles.chipMismatch,
      ]}
    >
      <Text style={styles.label} numberOfLines={1}>
        {label}
      </Text>
      <Text style={styles.value} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
        {value}
      </Text>
      {state !== 'neutral' && (
        <View
          style={[styles.dot, { backgroundColor: matched ? colors.teal : colors.amber }]}
        />
      )}
    </View>
  );
}

export function QuickFacts({ dog }: { dog: Dog }) {
  const md = dog.match_details;
  const stateFor = (key: 'gender' | 'age' | 'size'): MatchState => {
    const m = md?.[key];
    if (!m || !m.active) return 'neutral';
    return m.matched ? 'match' : 'mismatch';
  };

  return (
    <View style={styles.row}>
      <FactChip label="Sex" value={dogSex(dog)} state={stateFor('gender')} />
      <FactChip label="Age" value={dogAge(dog)} state={stateFor('age')} />
      <FactChip label="Weight" value={dogWeight(dog)} state={stateFor('size')} />
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 8,
  },
  chip: {
    flex: 1,
    minHeight: 60,
    paddingVertical: 10,
    paddingHorizontal: 6,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.chipBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipMatch: { backgroundColor: colors.tealBg, borderColor: colors.tealBorder },
  chipMismatch: { backgroundColor: colors.amberBg, borderColor: colors.amberBorder },
  label: {
    fontFamily: font.bold,
    fontSize: 10.5,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    color: colors.textFaint,
    marginBottom: 3,
  },
  value: {
    fontFamily: font.extrabold,
    fontSize: 13.5,
    color: colors.textMain,
    textAlign: 'center',
  },
  dot: {
    position: 'absolute',
    top: 7,
    right: 7,
    width: 7,
    height: 7,
    borderRadius: 4,
  },
});
