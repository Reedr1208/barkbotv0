import React, { useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ArrowLeft, Info, Send } from 'lucide-react-native';
import { api, ChatMessage } from '../../src/api';
import { useAuth } from '../../src/auth';
import { colors, font, radius, spacing } from '../../src/theme';
import { quickPrompts } from '../../src/utils';
import { ChatBubble, TypingDots } from '../../src/components/ChatBubble';
import { Pill } from '../../src/components/ui';

export default function ChatScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { email } = useAuth();
  const params = useLocalSearchParams<{ id: string; name?: string; image?: string }>();
  const animalId = String(params.id);
  const dogName = params.name ? String(params.name) : 'this dog';
  const dogImage = params.image ? String(params.image) : undefined;
  const dogInitial = dogName?.trim()?.[0] || '🐾';

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [showPrompts, setShowPrompts] = useState(true);
  const scrollRef = useRef<ScrollView>(null);

  // Load prior conversation (logged-in users only).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!email) {
        setLoadingHistory(false);
        return;
      }
      try {
        const { messages: prior } = await api.chatMessages(email, animalId);
        if (!cancelled && prior?.length) {
          setMessages(prior);
          setShowPrompts(false);
        }
      } catch {
        /* start fresh */
      } finally {
        if (!cancelled) setLoadingHistory(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [email, animalId]);

  const scrollToEnd = () => {
    requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
  };

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || sending) return;
    setInput('');
    setShowPrompts(false);

    const history = messages.slice(-12);
    const userMsg: ChatMessage = { role: 'user', content: message };
    setMessages((m) => [...m, userMsg]);
    setSending(true);
    scrollToEnd();

    try {
      const { reply } = await api.chat({
        animal_id: animalId,
        message,
        conversation_history: history,
        email: email ?? undefined,
        dog_name: dogName,
        dog_image_url: dogImage,
      });
      setMessages((m) => [...m, { role: 'assistant', content: reply }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: '_Sorry, I had trouble responding to that. Please try again._' },
      ]);
    } finally {
      setSending(false);
      scrollToEnd();
    }
  };

  const greeting = `Hi, I'm ${dogName}! 🐾 Ask me about my ideal home, energy level, or what to check with the shelter before we meet.`;
  const prompts = quickPrompts(dogName);

  return (
    <View style={styles.screen}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + 6 }]}>
        <Pressable accessibilityLabel="Back" onPress={() => router.back()} style={styles.backBtn} hitSlop={8}>
          <ArrowLeft size={22} color={colors.textMain} />
        </Pressable>
        <View style={styles.headerAvatar}>
          <Text style={styles.headerAvatarText}>{dogInitial.toUpperCase()}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerName} numberOfLines={1}>
            {dogName}
          </Text>
          <Text style={styles.headerSub}>AI companion · confirm details with shelter</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={styles.messages}
          onContentSizeChange={scrollToEnd}
          keyboardShouldPersistTaps="handled"
        >
          {/* Trust banner */}
          <View style={styles.trust}>
            <Info size={15} color={colors.amber} />
            <Text style={styles.trustText}>
              I can help you understand this dog's profile, but please confirm adoption, medical, and
              behavior details with the shelter.
            </Text>
          </View>

          {/* Greeting (local, not persisted) */}
          {messages.length === 0 && !loadingHistory && (
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
                <Pill key={p} label={p} onPress={() => send(p)} style={styles.promptPill} />
              ))}
            </View>
          )}
        </ScrollView>

        {/* Input bar */}
        <View style={[styles.inputBar, { paddingBottom: insets.bottom + 8 }]}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder={`Ask ${dogName} anything!`}
            placeholderTextColor={colors.textFaint}
            multiline
            onSubmitEditing={() => send(input)}
            returnKeyType="send"
            blurOnSubmit={false}
          />
          <Pressable
            accessibilityLabel="Send message"
            onPress={() => send(input)}
            disabled={!input.trim() || sending}
            style={[styles.sendBtn, (!input.trim() || sending) && styles.sendBtnDisabled]}
          >
            <Send size={20} color={colors.accentText} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.slate950 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingBottom: 10,
    backgroundColor: 'rgba(2,6,23,0.92)',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
  },
  backBtn: { padding: 4 },
  headerAvatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.teal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerAvatarText: { fontFamily: font.black, fontSize: 16, color: '#04201d' },
  headerName: { fontFamily: font.black, fontSize: 17, color: colors.textMain },
  headerSub: { fontFamily: font.medium, fontSize: 11.5, color: colors.textFaint },
  messages: { padding: spacing.lg, paddingBottom: spacing.xl },
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
    marginBottom: spacing.lg,
  },
  trustText: { flex: 1, fontFamily: font.medium, fontSize: 12.5, lineHeight: 18, color: colors.textMuted },
  prompts: { gap: 8, marginTop: 8 },
  promptPill: { alignSelf: 'flex-start' },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    backgroundColor: 'rgba(2,6,23,0.96)',
    borderTopWidth: 1,
    borderTopColor: colors.borderSoft,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    paddingHorizontal: spacing.lg,
    paddingTop: 12,
    paddingBottom: 12,
    color: colors.textMain,
    fontFamily: font.medium,
    fontSize: 16,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.4 },
});
