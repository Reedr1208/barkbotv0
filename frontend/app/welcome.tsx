import React, { useEffect, useRef, useState } from 'react';
import { Animated, ImageSourcePropType, ScrollView, StyleSheet, Text, View, useWindowDimensions, Platform } from 'react-native';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ShieldCheck } from 'lucide-react-native';
import { useAuth } from '../src/auth';
import { colors, font, radius, spacing } from '../src/theme';
import { Button } from '../src/components/ui';
import { trackEvent } from '../src/analytics';

interface Featured {
  name: string;
  quote: string;
  image: ImageSourcePropType;
}

const FEATURED: Featured[] = [
  {
    name: 'Spike',
    quote: "My foster called me a “dog from another planet” cuz my style is extraooo special, and I’m also a playyyful senior boy who loves zoomies, belly rubs, toys, fetch, tug, and car rides!!",
    image: require('../assets/featured/spike.jpg')
  },
  {
    name: 'Lulu',
    quote: "i think i’m a lot like baloo — easygoing, cozy, and always ready for a good couch snooze after some happy walkies 😌. but i’ve got a lil’ wise old soul too… like, “sometimes the best adventure is a soft bed and a kind hand.”",
    image: require('../assets/featured/lulu.jpg')
  },
  {
    name: 'Jack',
    quote: "😎 I’m Jack, 3 yrs old, 64 lbs of pure main-character energy, and I do have a big ol’ personality. I’m best when I get to come to you for pets on my own terms, and I need an experienced adult-only home that goes slow with me and helps me feel safe.",
    image: require('../assets/featured/jack.jpg')
  },
];

export default function Welcome() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { markVisited } = useAuth();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 768;

  const [idx, setIdx] = useState(0);
  const [typedQuote, setTypedQuote] = useState('');
  const fade = useRef(new Animated.Value(1)).current;

  // Track initial page view
  useEffect(() => {
    trackEvent('welcome_viewed');
  }, []);

  useEffect(() => {
    const dog = FEATURED[idx];
    const quote = dog.quote;
    
    // Reset typing state
    setTypedQuote('');
    
    // Fade in
    Animated.timing(fade, { toValue: 1, duration: 280, useNativeDriver: Platform.OS !== 'web' }).start();

    let textIndex = 0;
    let typingInterval: any = null;
    let nextSlideTimeout: any = null;

    const startTyping = () => {
      typingInterval = setInterval(() => {
        if (textIndex < quote.length) {
          setTypedQuote(quote.substring(0, textIndex + 1));
          textIndex++;
        } else {
          if (typingInterval) clearInterval(typingInterval);
          // Wait 3000ms after quote finishes typing before going to next dog
          nextSlideTimeout = setTimeout(() => {
            // Fade out, then change dog index
            Animated.timing(fade, { toValue: 0.1, duration: 280, useNativeDriver: Platform.OS !== 'web' }).start(() => {
              setIdx((i) => (i + 1) % FEATURED.length);
            });
          }, 3000);
        }
      }, 15);
    };

    // Begin typing sequence
    startTyping();

    return () => {
      if (typingInterval) clearInterval(typingInterval);
      if (nextSlideTimeout) clearTimeout(nextSlideTimeout);
    };
  }, [idx, fade]);

  const startSniffing = () => {
    trackEvent('start_sniffing_clicked');
    markVisited();
    router.replace('/discover');
  };

  const login = () => {
    trackEvent('login_clicked');
    router.push('/login');
  };

  const dog = FEATURED[idx];

  const leftPaneContent = (
    <View style={isDesktop ? styles.leftPane : null}>
      <Text style={styles.brand}>🐾 CHATTYHOUND</Text>
      <Text style={styles.title}>
        Meet adoptable dogs in a <Text style={styles.titleAccent}>whole new way</Text>.
      </Text>
      <Text style={styles.subtitle}>
        Chat with shelter dogs, discover their personality, and find the pup who fits your life.
      </Text>

      <View style={styles.ctaGroup}>
        <Button label="Start Sniffing 🐶" onPress={startSniffing} style={styles.cta} />
        <Button
          label="Sign In 🔑"
          variant="secondary"
          onPress={login}
          style={styles.cta}
        />
      </View>

      <View style={styles.banner}>
        <View style={styles.bannerHead}>
          <ShieldCheck size={18} color={colors.teal} />
          <Text style={styles.bannerTitle}>Shelter info comes first 🛡️</Text>
        </View>
        <Text style={styles.bannerBody}>
          ChattyHound is a playful AI companion to help you discover dogs. The official shelter page
          remains the absolute authority for all medical details, behavioral history, and adoption
          eligibility. ChattyHound is not necessarily affiliated with the shelters from which our listings are sourced.
        </Text>
      </View>
    </View>
  );

  const rightPaneContent = (
    <Animated.View style={[styles.heroCard, { opacity: fade }, isDesktop ? styles.desktopHeroCard : null]}>
      <Image source={dog.image} style={styles.heroImage} contentFit="cover" transition={250} />
      <View style={styles.quoteBubble}>
        <View style={styles.quoteHeader}>
          <Text style={styles.quoteName}>{dog.name}</Text>
          <Text style={styles.bubbleHeart}>❤️</Text>
        </View>
        <Text style={styles.quoteText}>“{typedQuote}”</Text>
      </View>
    </Animated.View>
  );

  if (isDesktop) {
    return (
      <View style={[styles.screen, styles.desktopScreen, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <View style={styles.desktopGrid}>
          {leftPaneContent}
          <View style={styles.rightPane}>
            {rightPaneContent}
          </View>
        </View>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl },
      ]}
    >
      {leftPaneContent}
      {rightPaneContent}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.slate950 },
  desktopScreen: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.xxl,
  },
  desktopGrid: {
    flexDirection: 'row',
    width: '100%',
    maxWidth: 1100,
    gap: spacing.xxl,
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.xl,
  },
  leftPane: {
    flex: 1.1,
    gap: spacing.lg,
    paddingRight: spacing.xl,
  },
  rightPane: {
    flex: 0.9,
    alignItems: 'center',
    justifyContent: 'center',
  },
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
  desktopHeroCard: {
    width: '100%',
    maxWidth: 420,
    aspectRatio: 1,
    marginVertical: 0,
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
  quoteHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  quoteName: { fontFamily: font.black, fontSize: 16, color: colors.accent },
  bubbleHeart: { fontSize: 16 },
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
