import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Info } from 'lucide-react-native';
import { api, ChatMessage, Dog } from '../api';
import { colors, font, radius, spacing } from '../theme';
import { quickPrompts, resolveDogImage } from '../utils';
import { ChatBubble, TypingDots } from './ChatBubble';
import { Pill } from './ui';

interface InlineChatProps {
  dog: Dog;
  email: string | null;
  onSendMessage: (text: string) => Promise<void>;
  messages: ChatMessage[];
  sending: boolean;
  loadingHistory: boolean;
}

export function InlineChat({
  dog,
  email,
  onSendMessage,
  messages,
  sending,
  loadingHistory,
}: InlineChatProps) {
  const [showPrompts, setShowPrompts] = useState(true);

  const dogName = dog.name || 'this dog';
  const dogInitial = dogName?.trim()?.[0] || '🐾';
  const greeting = `Hi, I'm ${dogName}! 🐾 Ask me about my ideal home, energy level, or what to check with the shelter before we meet.`;
  const prompts = quickPrompts(dogName);

  // Hide prompts when there are messages
  useEffect(() => {
    if (messages.length > 0) {
      setShowPrompts(false);
    } else {
      setShowPrompts(true);
    }
  }, [messages]);

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Chat with {dogName}</Text>
      </View>

      {/* Trust banner */}
      <View style={styles.trust}>
        <Info size={15} color={colors.amber} />
        <Text style={styles.trustText}>
          I can help you understand this dog's profile, but please confirm adoption, medical, and
          behavior details with the shelter.
        </Text>
      </View>

      {loadingHistory ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={colors.accent} size="small" />
          <Text style={styles.loadingText}>Loading conversation history...</Text>
        </View>
      ) : (
        <View style={styles.chatArea}>
          {/* Greeting (local, not persisted) */}
          {messages.length === 0 && (
            <ChatBubble role="assistant" content={greeting} dogInitial={dogInitial} />
          )}

          {messages.map((m, i) => (
            <ChatBubble key={i} role={m.role} content={m.content} dogInitial={dogInitial} />
          ))}

          {sending && <TypingDots dogInitial={dogInitial} />}

          {/* Quick prompts */}
          {showPrompts && !sending && (
            <View style={styles.prompts}>
              {prompts.map((p) => (
                <Pill
                  key={p}
                  label={p}
                  onPress={() => onSendMessage(p)}
                  style={styles.promptPill}
                />
              ))}
            </View>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.slate900,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    padding: spacing.lg,
    marginTop: spacing.md,
    gap: spacing.md,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    fontFamily: font.black,
    fontSize: 18,
    color: colors.textMain,
  },
  trust: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
    backgroundColor: colors.amberBg,
    borderWidth: 1,
    borderColor: colors.amberBorder,
    borderStyle: 'dashed',
    borderRadius: radius.sm,
    padding: spacing.md,
  },
  trustText: {
    flex: 1,
    fontFamily: font.medium,
    fontSize: 12,
    lineHeight: 17,
    color: colors.textMuted,
  },
  loadingWrap: {
    alignItems: 'center',
    paddingVertical: spacing.xl,
    gap: 8,
  },
  loadingText: {
    fontFamily: font.medium,
    fontSize: 13,
    color: colors.textFaint,
  },
  chatArea: {
    gap: spacing.md,
  },
  prompts: {
    gap: 8,
    marginTop: 4,
  },
  promptPill: {
    alignSelf: 'flex-start',
  },
});
