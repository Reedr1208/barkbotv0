import React, { useRef } from 'react';
import { Animated, Pressable, StyleSheet } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Heart } from 'lucide-react-native';
import { colors } from '../theme';

export function HeartButton({
  saved,
  onToggle,
  size = 48,
}: {
  saved: boolean;
  onToggle: () => void;
  size?: number;
}) {
  const scale = useRef(new Animated.Value(1)).current;

  const handlePress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    Animated.sequence([
      Animated.timing(scale, { toValue: 1.35, duration: 120, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 4, useNativeDriver: true }),
    ]).start();
    onToggle();
  };

  const iconSize = Math.round(size * 0.46);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={saved ? 'Remove from saved dogs' : 'Save this dog'}
      onPress={handlePress}
      style={[
        styles.btn,
        { width: size, height: size, borderRadius: size / 2 },
        saved && styles.btnSaved,
      ]}
    >
      <Animated.View style={{ transform: [{ scale }] }}>
        <Heart
          size={iconSize}
          color={saved ? colors.accent : '#64748b'}
          fill={saved ? colors.accent : 'transparent'}
          strokeWidth={2.4}
        />
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    backgroundColor: colors.cream,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 4,
  },
  btnSaved: {
    shadowColor: colors.accent,
    shadowOpacity: 0.45,
    shadowRadius: 16,
  },
});
