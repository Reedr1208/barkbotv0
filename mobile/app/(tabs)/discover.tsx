import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { SlidersHorizontal, Shuffle } from 'lucide-react-native';
import { api, ApiError, Dog } from '../../src/api';
import { useAuth } from '../../src/auth';
import { colors, font, radius, spacing } from '../../src/theme';
import { resolveDogImage } from '../../src/utils';
import { DogProfileView } from '../../src/components/DogProfileView';
import { EmptyState } from '../../src/components/common';

export default function Discover() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { email, isLoggedIn, preferences, savePreferences } = useAuth();

  const [dog, setDog] = useState<Dog | null>(null);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const viewedRef = useRef<string[]>([]);
  const reqId = useRef(0);

  const prefsKey = `${email}|${preferences.gender}|${preferences.age_group}|${preferences.size}|${preferences.location}`;

  const fetchDog = useCallback(async () => {
    const myReq = ++reqId.current;
    setLoading(true);
    setError(null);
    setEmpty(false);
    try {
      const params = isLoggedIn
        ? { email: email ?? undefined, viewed: viewedRef.current }
        : {
            gender: preferences.gender,
            age_group: preferences.age_group,
            size: preferences.size,
            location: preferences.location,
            viewed: viewedRef.current,
          };
      const next = await api.randomDog(params);
      if (myReq !== reqId.current) return; // superseded
      setDog(next);
      if (next?.animal_id && !viewedRef.current.includes(next.animal_id)) {
        viewedRef.current = [...viewedRef.current, next.animal_id].slice(-40);
      }
    } catch (e) {
      if (myReq !== reqId.current) return;
      if (e instanceof ApiError && e.status === 404) {
        setEmpty(true);
        setDog(null);
      } else {
        setError(e instanceof Error ? e.message : 'Something went wrong.');
      }
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  }, [email, isLoggedIn, preferences.gender, preferences.age_group, preferences.size, preferences.location]);

  // Refetch whenever identity/preferences change (also covers first mount).
  useEffect(() => {
    viewedRef.current = [];
    fetchDog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefsKey]);

  const openChat = (d: Dog) => {
    router.push({
      pathname: '/chat/[id]',
      params: { id: d.animal_id, name: d.name, image: resolveDogImage(d) ?? '' },
    });
  };

  const showAllDogs = async () => {
    await savePreferences({ gender: 'any', age_group: 'any', size: 'any', location: 'any' });
    // prefsKey change triggers refetch
  };

  return (
    <View style={styles.screen}>
      {/* Sticky header */}
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.brand}>ChattyHound</Text>
          <Text style={styles.tagline}>Find your match</Text>
        </View>
        <Pressable
          accessibilityLabel="Preferences"
          onPress={() => router.push('/profile')}
          style={styles.iconBtn}
        >
          <SlidersHorizontal size={18} color={colors.textMain} />
        </Pressable>
        <Pressable
          accessibilityLabel="Next dog"
          onPress={fetchDog}
          disabled={loading}
          style={styles.nextBtn}
        >
          <Shuffle size={16} color={colors.accentText} />
          <Text style={styles.nextBtnText}>Next Dog</Text>
        </Pressable>
      </View>

      {loading && !dog ? (
        <DogSkeleton />
      ) : empty ? (
        <EmptyState
          title="No perfect matches yet"
          description="Every rescue pup has unique charm! We don't have a dog matching your exact preferences right now, but we update constantly. Try adjusting your preferences or exploring all dogs."
          primaryLabel="Adjust Preferences 🛠️"
          onPrimary={() => router.push('/profile')}
          secondaryLabel="Show me all dogs"
          onSecondary={showAllDogs}
        />
      ) : error ? (
        <EmptyState
          icon="😕"
          title="Couldn't load a dog"
          description={error}
          primaryLabel="Try again"
          onPrimary={fetchDog}
        />
      ) : dog ? (
        <ScrollView
          contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}
          showsVerticalScrollIndicator={false}
        >
          <DogProfileView dog={dog} onChat={() => openChat(dog)} />
          <View style={styles.shuffleFooter}>
            <Pressable style={styles.shuffleBig} onPress={fetchDog} disabled={loading}>
              {loading ? (
                <ActivityIndicator color={colors.textMain} />
              ) : (
                <>
                  <Shuffle size={18} color={colors.textMain} />
                  <Text style={styles.shuffleBigText}>Show me another dog</Text>
                </>
              )}
            </Pressable>
          </View>
        </ScrollView>
      ) : null}
    </View>
  );
}

function DogSkeleton() {
  return (
    <View>
      <View style={skeleton.hero} />
      <View style={{ padding: spacing.xl, gap: spacing.md }}>
        <View style={[skeleton.block, { height: 84 }]} />
        <View style={[skeleton.block, { height: 70 }]} />
        <View style={[skeleton.block, { height: 120 }]} />
        <View style={{ alignItems: 'center', marginTop: 12 }}>
          <ActivityIndicator color={colors.accent} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.slate950 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: 10,
    backgroundColor: 'rgba(2,6,23,0.92)',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
  },
  brand: { fontFamily: font.black, fontSize: 18, color: colors.textMain, letterSpacing: -0.3 },
  tagline: { fontFamily: font.semibold, fontSize: 12, color: colors.textFaint },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  nextBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.accent,
    paddingHorizontal: 14,
    height: 40,
    borderRadius: radius.pill,
  },
  nextBtnText: { fontFamily: font.extrabold, fontSize: 13.5, color: colors.accentText },
  shuffleFooter: { paddingHorizontal: spacing.xl, paddingTop: spacing.sm },
  shuffleBig: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    height: 50,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.borderSoft,
    backgroundColor: colors.surfaceFaint,
  },
  shuffleBigText: { fontFamily: font.extrabold, fontSize: 14.5, color: colors.textMain },
});

const skeleton = StyleSheet.create({
  hero: { height: 320, backgroundColor: colors.slate800 },
  block: {
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
});
