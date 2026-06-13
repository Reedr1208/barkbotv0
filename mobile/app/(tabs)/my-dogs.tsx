import React, { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { useFocusEffect, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Heart } from 'lucide-react-native';
import { api, ConversationSummary } from '../../src/api';
import { FavoriteDog, useAuth } from '../../src/auth';
import { colors, font, radius, spacing } from '../../src/theme';
import { relativeTime } from '../../src/utils';
import { EmptyState } from '../../src/components/common';
import { Button } from '../../src/components/ui';

type Tab = 'saved' | 'recent';

export default function MyDogs() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { email, isLoggedIn, favorites, refreshFavorites, toggleFavorite } = useAuth();
  const [tab, setTab] = useState<Tab>('saved');
  const [convos, setConvos] = useState<ConversationSummary[]>([]);
  const [loadingConvos, setLoadingConvos] = useState(false);

  useFocusEffect(
    useCallback(() => {
      refreshFavorites();
      if (email) {
        setLoadingConvos(true);
        api
          .conversations(email)
          .then(({ conversations }) => setConvos(conversations || []))
          .catch(() => setConvos([]))
          .finally(() => setLoadingConvos(false));
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [email])
  );

  const savedList = Object.values(favorites);

  const openChat = (animalId: string, name: string, image?: string) =>
    router.push({ pathname: '/chat/[id]', params: { id: animalId, name, image: image ?? '' } });

  const openProfile = (animalId: string) =>
    router.push({ pathname: '/dogs/[...slug]', params: { slug: animalId } });

  return (
    <View style={styles.screen}>
      <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
        <Text style={styles.title}>My Dogs</Text>
        <Text style={styles.subtitle}>Dogs you've hearted and conversations you can continue.</Text>
        <View style={styles.tabs}>
          <TabButton label="❤️ Saved Dogs" active={tab === 'saved'} onPress={() => setTab('saved')} />
          <TabButton label="💬 Recent Chats" active={tab === 'recent'} onPress={() => setTab('recent')} />
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}>
        {tab === 'saved' ? (
          savedList.length === 0 ? (
            <EmptyState
              icon="🐾"
              title="No saved dogs yet"
              description="Tap the heart on any dog to keep them here. Start exploring to find your match!"
              primaryLabel="Discover dogs"
              onPrimary={() => router.push('/discover')}
            />
          ) : (
            <View style={styles.list}>
              {savedList.map((d) => (
                <SavedCard
                  key={d.animal_id}
                  dog={d}
                  onChat={() => openChat(d.animal_id, d.dog_name, d.dog_image_url)}
                  onProfile={() => openProfile(d.animal_id)}
                  onRemove={() => toggleFavorite(d)}
                />
              ))}
              <Text style={styles.footNote}>
                Missing a dog? Listings may be cleared when a shelter page is no longer available.
              </Text>
            </View>
          )
        ) : !isLoggedIn ? (
          <EmptyState
            icon="🔑"
            title="Sign in to see your chats"
            description="Recent conversations are saved to your account so you can continue them on any device."
            primaryLabel="Sign In"
            onPrimary={() => router.push('/login')}
          />
        ) : loadingConvos ? (
          <Text style={styles.loading}>Loading conversations…</Text>
        ) : convos.length === 0 ? (
          <EmptyState
            icon="💬"
            title="No conversations yet"
            description="Start chatting with a dog and your recent chats will appear here."
            primaryLabel="Discover dogs"
            onPrimary={() => router.push('/discover')}
          />
        ) : (
          <View style={styles.list}>
            {convos.map((c) => (
              <Pressable
                key={c.animal_id}
                style={styles.convoRow}
                onPress={() => openChat(c.animal_id, c.dog_name, c.dog_image_url)}
              >
                <Avatar uri={c.dog_image_url} name={c.dog_name} />
                <View style={{ flex: 1 }}>
                  <View style={styles.convoTop}>
                    <Text style={styles.convoName} numberOfLines={1}>
                      {c.dog_name || 'Dog'}
                    </Text>
                    <Text style={styles.convoTime}>{relativeTime(c.updated_at)}</Text>
                  </View>
                  <Text style={styles.convoPreview} numberOfLines={1}>
                    {c.last_message_preview || 'Tap to continue the conversation'}
                  </Text>
                </View>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

function TabButton({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.tabBtn, active && styles.tabBtnActive]}>
      <Text style={[styles.tabBtnText, active && styles.tabBtnTextActive]}>{label}</Text>
    </Pressable>
  );
}

function Avatar({ uri, name }: { uri?: string; name?: string }) {
  if (uri) return <Image source={{ uri }} style={styles.avatar} contentFit="cover" />;
  return (
    <View style={[styles.avatar, styles.avatarFallback]}>
      <Text style={styles.avatarText}>{(name?.[0] || '🐾').toUpperCase()}</Text>
    </View>
  );
}

function SavedCard({
  dog,
  onChat,
  onProfile,
  onRemove,
}: {
  dog: FavoriteDog;
  onChat: () => void;
  onProfile: () => void;
  onRemove: () => void;
}) {
  return (
    <View style={styles.card}>
      <Pressable onPress={onProfile} style={styles.cardMain}>
        <Avatar uri={dog.dog_image_url} name={dog.dog_name} />
        <View style={{ flex: 1 }}>
          <Text style={styles.cardName} numberOfLines={1}>
            {dog.dog_name}
          </Text>
          <Text style={styles.cardSub} numberOfLines={1}>
            {[dog.shelter_name, dog.age].filter(Boolean).join(' · ') || dog.animal_id}
          </Text>
        </View>
        <Pressable onPress={onRemove} hitSlop={8} style={styles.removeBtn} accessibilityLabel="Remove">
          <Heart size={20} color={colors.accent} fill={colors.accent} />
        </Pressable>
      </Pressable>
      <Button label="Continue Chat" onPress={onChat} style={styles.chatBtn} textStyle={{ fontSize: 13.5 }} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.slate950 },
  header: {
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
    backgroundColor: 'rgba(2,6,23,0.92)',
  },
  title: { fontFamily: font.black, fontSize: 26, color: colors.textMain, letterSpacing: -0.5 },
  subtitle: { fontFamily: font.medium, fontSize: 13, color: colors.textMuted, marginTop: 2 },
  tabs: { flexDirection: 'row', gap: 8, marginTop: spacing.md },
  tabBtn: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  tabBtnActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  tabBtnText: { fontFamily: font.bold, fontSize: 13, color: colors.textMuted },
  tabBtnTextActive: { color: colors.accentText },
  list: { padding: spacing.xl, gap: spacing.md },
  loading: { fontFamily: font.medium, color: colors.textMuted, textAlign: 'center', marginTop: 40 },
  footNote: {
    fontFamily: font.regular,
    fontSize: 12,
    color: colors.textFaint,
    textAlign: 'center',
    marginTop: 8,
  },
  card: {
    backgroundColor: colors.surfaceFaint,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  cardMain: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  cardName: { fontFamily: font.extrabold, fontSize: 16, color: colors.textMain },
  cardSub: { fontFamily: font.medium, fontSize: 12.5, color: colors.textFaint, marginTop: 2 },
  removeBtn: { padding: 4 },
  chatBtn: { alignSelf: 'stretch', minHeight: 42 },
  avatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.slate800 },
  avatarFallback: { alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontFamily: font.black, fontSize: 20, color: colors.accent },
  convoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surfaceFaint,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radius.lg,
    padding: spacing.md,
  },
  convoTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  convoName: { fontFamily: font.extrabold, fontSize: 15.5, color: colors.textMain, flex: 1 },
  convoTime: { fontFamily: font.medium, fontSize: 11.5, color: colors.textFaint },
  convoPreview: { fontFamily: font.regular, fontSize: 13, color: colors.textMuted, marginTop: 2 },
});
