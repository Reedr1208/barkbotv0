import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ArrowLeft } from 'lucide-react-native';
import { api, ApiError, Dog } from '../../src/api';
import { colors, font, spacing } from '../../src/theme';
import { resolveDogImage } from '../../src/utils';
import { DogProfileView } from '../../src/components/DogProfileView';
import { EmptyState } from '../../src/components/common';

/**
 * Deep-link target for shared links: chattyhound.com/dogs/:id and
 * chattyhound.com/dogs/:location/:id (matches the web's rewrite rules).
 */
export default function DogDetail() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { slug } = useLocalSearchParams<{ slug: string | string[] }>();

  const segments = Array.isArray(slug) ? slug : String(slug ?? '').split('/').filter(Boolean);
  const animalId = segments.length ? segments[segments.length - 1] : '';
  const isAllDogs = animalId === 'alldogs' || animalId === '';

  const [dog, setDog] = useState<Dog | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (isAllDogs) {
      router.replace('/discover');
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .randomDog({ animal_id: animalId })
      .then((d) => {
        if (!cancelled) setDog(d);
      })
      .catch((e) => {
        if (!cancelled) {
          if (e instanceof ApiError && e.status === 404) setUnavailable(true);
          else setUnavailable(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animalId]);

  const goDiscover = () => router.replace('/discover');
  const openChat = (d: Dog) =>
    router.push({ pathname: '/chat/[id]', params: { id: d.animal_id, name: d.name, image: resolveDogImage(d) ?? '' } });

  return (
    <View style={styles.screen}>
      <View style={[styles.header, { paddingTop: insets.top + 6 }]}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : goDiscover())} hitSlop={8} style={styles.back}>
          <ArrowLeft size={22} color={colors.textMain} />
        </Pressable>
        <Text style={styles.headerTitle}>{dog?.name ?? 'Adoptable dog'}</Text>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : unavailable || !dog ? (
        <EmptyState
          icon="🐾"
          title="This dog may no longer be available"
          description="Shelters update listings often. You can meet other adoptable dogs on ChattyHound right now."
          primaryLabel="Meet other dogs"
          onPrimary={goDiscover}
        />
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 24 }} showsVerticalScrollIndicator={false}>
          <DogProfileView dog={dog} onChat={() => openChat(dog)} />
        </ScrollView>
      )}
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
  back: { padding: 4 },
  headerTitle: { fontFamily: font.black, fontSize: 17, color: colors.textMain },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
