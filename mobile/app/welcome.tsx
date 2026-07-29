import React, { useEffect, useRef, useState } from 'react';
import { Animated, ImageSourcePropType, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ShieldCheck } from 'lucide-react-native';
import { useAuth } from '../src/auth';
import { colors, font, radius, spacing } from '../src/theme';
import { Button } from '../src/components/ui';

interface Featured {
  name: string;
  quote: string;
  image: ImageSourcePropType;
}

const FEATURED: Featured[] = [
  { name: 'Spike', quote: "I'm a couch-cuddle champion looking for my person.", image: require('../assets/featured/spike.jpg') },
  { name: 'Lulu', quote: 'Walks, snacks, naps — repeat. Want to join me?', image: require('../assets/featured/lulu.jpg') },
  { name: 'Jack', quote: 'Loyal sidekick energy. Ready when you are!', image: require('../assets/featured/jack.jpg') },
];

export default function Welcome() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { markVisited } = useAuth();
  const [idx, setIdx] = useState(0);
  const fade = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    const timer = setInterval(() => {
      Animated.timing(fade, { toValue: 0, duration: 280, useNativeDriver: true }).start(() => {
        setIdx((i) => (i + 1) % FEATURED.length);
        Animated.timing(fade, { toValue: 1, duration: 280, useNativeDriver: true }).start();
      });
    }, 3500);
    return () => clearInterval(timer);
  }, [fade]);

  const startSniffing = () => {
    markVisited();
    router.replace('/discover');
  };

  const dog = FEATURED[idx];

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl },
      ]}
    >
      <Text style={styles.brand}>🐾 CHATTYHOUND</Text>
      <Text style={styles.title}>
        Meet adoptable dogs in a <Text style={styles.titleAccent}>whole new way</Text>
      </Text>
      <Text style={styles.subtitle}>
        Chat with shelter dogs, discover their personality, and find the pup who fits your life.
      </Text>

      <Animated.View style={[styles.heroCard, { opacity: fade }]}>
        <Image source={dog.image} style={styles.heroImage} contentFit="cover" transition={250} />
        <View style={styles.quoteBubble}>
          <Text style={styles.quoteName}>{dog.name}</Text>
          <Text style={styles.quoteText}>“{dog.quote}”</Text>
        </View>
      </Animated.View>

      <View style={styles.ctaGroup}>
        <Button label="Start Sniffing 🐶" onPress={startSniffing} style={styles.cta} />
        <Button
          label="Sign In 🔑"
          variant="secondary"
          onPress={() => router.push('/login')}
          style={styles.cta}
        />
      </View>

      <View style={styles.banner}>
        <View style={styles.bannerHead}>
          <ShieldCheck size={18} color={colors.teal} />
          <Text style={styles.bannerTitle}>Shelter info comes first</Text>
        </View>
        <Text style={styles.bannerBody}>
          ChattyHound is a playful AI companion to help you discover dogs. The official shelter page
          remains the authority for all medical details, behavioral history, and adoption
          eligibility.
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.slate950 },
  content: { paddingHorizontal: spacing.xl, gap: spacing.lg },
  brand: {
    fontFamily: font.black,
    fontSize: 12,
    letterSpacing: 3,
    color: colors.textFaint,
  },
  title: { fontFamily: font.black, fontSize: 34, lineHeight: 40, color: colors.textMain, letterSpacing: -1 },
  titleAccent: { color: colors.accent },
  subtitle: { fontFamily: font.medium, fontSize: 15.5, lineHeight: 23, color: colors.textMuted },
  heroCard: {
    borderRadius: radius.xl,
    overflow: 'hidden',
    backgroundColor: colors.slate800,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  heroImage: { width: '100%', aspectRatio: 1 },
  quoteBubble: {
    position: 'absolute',
    left: spacing.lg,
    right: spacing.lg,
    bottom: spacing.lg,
    backgroundColor: 'rgba(2,6,23,0.82)',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    padding: spacing.md,
  },
  quoteName: { fontFamily: font.black, fontSize: 16, color: colors.accent, marginBottom: 2 },
  quoteText: { fontFamily: font.semibold, fontSize: 14, lineHeight: 20, color: colors.textMain },
  ctaGroup: { gap: spacing.sm },
  cta: { alignSelf: 'stretch' },
  banner: {
    backgroundColor: colors.tealBg,
    borderWidth: 1.5,
    borderColor: colors.tealBorder,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  bannerHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  bannerTitle: { fontFamily: font.extrabold, fontSize: 14.5, color: colors.textMain },
  bannerBody: { fontFamily: font.regular, fontSize: 13.5, lineHeight: 20, color: colors.textMuted },
});
