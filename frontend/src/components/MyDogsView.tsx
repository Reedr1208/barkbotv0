import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { Heart } from 'lucide-react-native';
import { api, ConversationSummary } from '../api';
import { FavoriteDog, useAuth } from '../auth';
import { colors, font, radius, spacing } from '../theme';
import { relativeTime } from '../utils';
import { EmptyState } from './common';
import { Button } from './ui';

type Tab = 'saved' | 'recent';

interface MyDogsViewProps {
  onSelectDog?: (animalId: string, name: string, image?: string) => void;
  onClose?: () => void;
}

export function MyDogsView({ onSelectDog, onClose }: MyDogsViewProps) {
  const router = useRouter();
  const { email, isLoggedIn, favorites, refreshFavorites, toggleFavorite } = useAuth();
  const [tab, setTab] = useState<Tab>('saved');
  const [convos, setConvos] = useState<ConversationSummary[]>([]);
  const [loadingConvos, setLoadingConvos] = useState(false);

  // Load convos and refresh favorites
  const loadData = useCallback(() => {
    refreshFavorites();
    if (email) {
      setLoadingConvos(true);
      api
        .conversations(email)
        .then(({ conversations }) => setConvos(conversations || []))
        .catch(() => setConvos([]))
        .finally(() => setLoadingConvos(false));
    }
  }, [email, refreshFavorites]);

  // Run on mount / tab change
  useEffect(() => {
    loadData();
  }, [loadData, tab]);

  const savedList = Object.values(favorites);

  const handleSelect = (animalId: string, name: string, image?: string) => {
    if (onSelectDog) {
      onSelectDog(animalId, name, image);
    } else {
      if (onClose) onClose();
      // Router fallback if no custom callback
      router.push({ pathname: `/dogs/[...slug]`, params: { slug: [animalId] } });
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>My Dogs</Text>
        <Text style={styles.subtitle}>Dogs you've hearted and conversations you can continue.</Text>
        <View style={styles.tabs}>
          <TabButton label="❤️ Saved Dogs" active={tab === 'saved'} onPress={() => setTab('saved')} />
          <TabButton label="💬 Recent Chats" active={tab === 'recent'} onPress={() => setTab('recent')} />
        </View>
      </View>

      <ScrollView 
        style={styles.scroll} 
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {tab === 'saved' ? (
          savedList.length === 0 ? (
            <EmptyState
              icon="🐾"
              title="No saved dogs yet"
              description="Tap the heart on any dog to keep them here. Start exploring to find your match!"
              primaryLabel="Discover dogs"
              onPrimary={() => {
                if (onClose) onClose();
                router.push('/discover');
              }}
            />
          ) : (
            <View style={styles.list}>
              {savedList.map((d) => (
                <SavedCard
                  key={d.animal_id}
                  dog={d}
                  onChat={() => handleSelect(d.animal_id, d.dog_name, d.dog_image_url)}
                  onProfile={() => handleSelect(d.animal_id, d.dog_name, d.dog_image_url)}
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
            onPrimary={() => {
              if (onClose) onClose();
              router.push('/login');
            }}
          />
        ) : loadingConvos ? (
          <View style={styles.loaderWrap}>
            <ActivityIndicator color={colors.accent} size="small" />
            <Text style={styles.loading}>Loading conversations…</Text>
          </View>
        ) : convos.length === 0 ? (
          <EmptyState
            icon="💬"
            title="No conversations yet"
            description="Start chatting with a dog and your recent chats will appear here."
            primaryLabel="Discover dogs"
            onPrimary={() => {
              if (onClose) onClose();
              router.push('/discover');
            }}
          />
        ) : (
          <View style={styles.list}>
            {convos.map((c) => (
              <Pressable
                key={c.animal_id}
                style={styles.convoRow}
                onPress={() => handleSelect(c.animal_id, c.dog_name, c.dog_image_url)}
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
          <Heart size={18} color={colors.accent} fill={colors.accent} />
        </Pressable>
      </Pressable>
      <Button label="Continue Chat" onPress={onChat} style={styles.chatBtn} textStyle={{ fontSize: 13 }} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    maxHeight: '100%',
  },
  header: {
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
  },
  title: {
    fontFamily: font.black,
    fontSize: 22,
    color: colors.textMain,
    letterSpacing: -0.5,
  },
  subtitle: {
    fontFamily: font.medium,
    fontSize: 13,
    color: colors.textMuted,
    marginTop: 4,
  },
  tabs: {
    flexDirection: 'row',
    gap: 8,
    marginTop: spacing.md,
  },
  tabBtn: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  tabBtnActive: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  tabBtnText: {
    fontFamily: font.bold,
    fontSize: 12.5,
    color: colors.textMuted,
  },
  tabBtnTextActive: {
    color: colors.accentText,
  },
  scroll: {
    maxHeight: 400,
  },
  scrollContent: {
    paddingTop: spacing.md,
    paddingBottom: spacing.xl,
  },
  list: {
    gap: spacing.md,
  },
  loaderWrap: {
    alignItems: 'center',
    paddingVertical: 32,
    gap: 8,
  },
  loading: {
    fontFamily: font.medium,
    color: colors.textMuted,
    fontSize: 13,
  },
  footNote: {
    fontFamily: font.regular,
    fontSize: 11.5,
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
    gap: spacing.sm,
  },
  cardMain: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  cardName: {
    fontFamily: font.extrabold,
    fontSize: 15,
    color: colors.textMain,
  },
  cardSub: {
    fontFamily: font.medium,
    fontSize: 12,
    color: colors.textFaint,
    marginTop: 2,
  },
  removeBtn: {
    padding: 4,
  },
  chatBtn: {
    alignSelf: 'stretch',
    minHeight: 36,
    borderRadius: radius.sm,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.slate800,
  },
  avatarFallback: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    fontFamily: font.black,
    fontSize: 18,
    color: colors.accent,
  },
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
  convoTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  convoName: {
    fontFamily: font.extrabold,
    fontSize: 14.5,
    color: colors.textMain,
    flex: 1,
  },
  convoTime: {
    fontFamily: font.medium,
    fontSize: 11,
    color: colors.textFaint,
  },
  convoPreview: {
    fontFamily: font.regular,
    fontSize: 12.5,
    color: colors.textMuted,
    marginTop: 2,
  },
});
