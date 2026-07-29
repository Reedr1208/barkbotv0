import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { colors, font, radius } from '../theme';

function Avatar({ initial }: { initial: string }) {
  return (
    <View style={styles.avatar}>
      <Text style={styles.avatarText}>{initial.toUpperCase()}</Text>
    </View>
  );
}

export function ChatBubble({
  role,
  content,
  dogInitial,
}: {
  role: 'user' | 'assistant';
  content: string;
  dogInitial: string;
}) {
  if (role === 'user') {
    return (
      <View style={[styles.row, styles.rowUser]}>
        <View style={[styles.bubble, styles.userBubble]}>
          <Text style={styles.userText}>{content}</Text>
        </View>
      </View>
    );
  }
  return (
    <View style={[styles.row, styles.rowBot]}>
      <Avatar initial={dogInitial || '🐾'} />
      <View style={[styles.bubble, styles.botBubble]}>
        <Markdown style={markdownStyles}>{content}</Markdown>
      </View>
    </View>
  );
}

export function TypingDots({ dogInitial }: { dogInitial: string }) {
  const dot0 = useRef(new Animated.Value(0.3)).current;
  const dot1 = useRef(new Animated.Value(0.3)).current;
  const dot2 = useRef(new Animated.Value(0.3)).current;
  const dots = [dot0, dot1, dot2];

  useEffect(() => {
    const animations = dots.map((d, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 160),
          Animated.timing(d, { toValue: 1, duration: 400, useNativeDriver: true }),
          Animated.timing(d, { toValue: 0.3, duration: 400, useNativeDriver: true }),
        ])
      )
    );
    animations.forEach((a) => a.start());
    return () => animations.forEach((a) => a.stop());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <View style={[styles.row, styles.rowBot]}>
      <Avatar initial={dogInitial || '🐾'} />
      <View style={[styles.bubble, styles.botBubble, styles.typingBubble]}>
        {dots.map((d, i) => (
          <Animated.View key={i} style={[styles.dot, { opacity: d }]} />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', marginBottom: 12, gap: 8, alignItems: 'flex-end' },
  rowUser: { justifyContent: 'flex-end' },
  rowBot: { justifyContent: 'flex-start' },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.teal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { fontFamily: font.black, fontSize: 14, color: '#04201d' },
  bubble: {
    maxWidth: '78%',
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: radius.bubble,
  },
  botBubble: {
    backgroundColor: colors.slate800,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderTopLeftRadius: 4,
  },
  userBubble: {
    backgroundColor: colors.accent,
    borderTopRightRadius: 4,
  },
  userText: { fontFamily: font.semibold, fontSize: 14.5, lineHeight: 20, color: colors.accentText },
  typingBubble: { flexDirection: 'row', gap: 5, alignItems: 'center', paddingVertical: 14 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.textMuted },
});

const markdownStyles = {
  body: { color: colors.textOnBubble, fontFamily: font.regular, fontSize: 14.5, lineHeight: 21 },
  strong: { fontFamily: font.extrabold, color: colors.textOnBubble },
  em: { fontStyle: 'italic' as const },
  bullet_list: { marginTop: 2 },
  ordered_list: { marginTop: 2 },
  list_item: { marginVertical: 2 },
  paragraph: { marginTop: 0, marginBottom: 8 },
  link: { color: colors.accent },
} as const;
