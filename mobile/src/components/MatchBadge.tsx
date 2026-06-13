import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { AlertTriangle, Sparkles } from 'lucide-react-native';
import { colors, font, radius } from '../theme';

export function MatchBadge({ strong }: { strong: boolean }) {
  return (
    <View style={[styles.badge, strong ? styles.strong : styles.potential]}>
      {strong ? (
        <Sparkles size={14} color={colors.teal} />
      ) : (
        <AlertTriangle size={14} color={colors.amber} />
      )}
      <Text style={[styles.text, { color: strong ? colors.teal : colors.amber }]}>
        {strong ? 'Strong match' : 'Potential match'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    alignSelf: 'flex-start',
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  strong: { backgroundColor: colors.tealBg, borderColor: colors.tealBorder },
  potential: { backgroundColor: colors.amberBg, borderColor: colors.amberBorder },
  text: {
    fontFamily: font.black,
    fontSize: 12.5,
  },
});
