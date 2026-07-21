import React, { useState } from 'react';
import { Linking, Pressable, Share, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import {
  CalendarClock,
  ExternalLink,
  MapPin,
  MessageCircle,
  Share2,
  ShieldAlert,
} from 'lucide-react-native';
import { ChatMessage, Dog } from '../api';
import { colors, font, radius, spacing } from '../theme';
import {
  dogBio,
  dogShareMessage,
  dogShareUrl,
  dogTraits,
  freshnessLabel,
  isStrongMatch,
  resolveDogImage,
} from '../utils';
import { useAuth } from '../auth';
import { useToast } from '../toast';
import { Card, Pill, SectionLabel } from './ui';
import { HeartButton } from './HeartButton';
import { MatchBadge } from './MatchBadge';
import { QuickFacts } from './QuickFacts';
import { InlineChat } from './InlineChat';

const SUPPORT_EMAIL = 'hello@chattyhound.com';

// ---------------------------------------------------------------------------
// 1. DogHeroView Component
// ---------------------------------------------------------------------------

interface DogHeroViewProps {
  dog: Dog;
  isDesktop?: boolean;
}

export function DogHeroView({ dog, isDesktop = false }: DogHeroViewProps) {
  const { isFavorite, toggleFavorite } = useAuth();
  const toast = useToast();

  const image = resolveDogImage(dog);
  const strong = isStrongMatch(dog);
  const saved = isFavorite(dog.animal_id);

  const handleHeart = async () => {
    const nowSaved = await toggleFavorite({
      animal_id: dog.animal_id,
      dog_name: dog.name,
      dog_image_url: image,
      shelter_name: dog.shelter_name,
      shelter_profile_url: dog.shelter_url,
      age: dog.age,
      gender: dog.sex || dog.gender,
      weight: dog.weight,
    });
    toast.show(nowSaved ? '❤️ Added to favorites!' : '💔 Removed from favorites');
  };

  const handleShare = async () => {
    try {
      await Share.share({
        message: dogShareMessage(dog.name, dog.animal_id),
        url: dogShareUrl(dog.animal_id),
        title: `Meet ${dog.name} on ChattyHound`,
      });
    } catch {
      /* user dismissed */
    }
  };

  const locationText = dog.shelter_name || dog.located_at || '';

  return (
    <View style={[styles.hero, isDesktop && styles.heroDesktop]}>
      {image ? (
        <Image
          source={{ uri: image }}
          style={[styles.heroImage, isDesktop && styles.heroImageDesktop]}
          contentFit="cover"
          transition={200}
        />
      ) : (
        <View style={[styles.heroImage, styles.heroPlaceholder, isDesktop && styles.heroImageDesktop]}>
          <Text style={styles.heroPlaceholderText}>🐾</Text>
        </View>
      )}
      <LinearGradient
        colors={['transparent', 'rgba(15,23,42,0.7)', colors.slate900] as [string, string, string]}
        locations={[0, 0.55, 1] as [number, number, number]}
        style={[styles.heroOverlay, isDesktop && styles.heroOverlayDesktop]}
      />
      <View style={styles.heroContent}>
        <View style={styles.heroTextCol}>
          <MatchBadge strong={strong} />
          <Text style={styles.dogName} numberOfLines={1}>
            {dog.name}
          </Text>
          <View style={styles.metaRow}>
            {!!locationText && <MapPin size={13} color={colors.accent} />}
            <Text style={styles.metaText} numberOfLines={1}>
              {locationText ? `${locationText}` : ''}
              {locationText ? '  •  ' : ''}
              {dog.animal_id}
            </Text>
          </View>
        </View>
        <View style={styles.heroActions}>
          <Pressable
            accessibilityLabel="Share this dog"
            accessibilityRole="button"
            onPress={handleShare}
            style={styles.shareBtn}
          >
            <Share2 size={20} color={colors.white} />
          </Pressable>
          <HeartButton saved={saved} onToggle={handleHeart} />
        </View>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// 2. DogDetailsView Component
// ---------------------------------------------------------------------------

interface DogDetailsViewProps {
  dog: Dog;
  email: string | null;
  onChat: () => void;
  onSendMessage: (text: string) => Promise<void>;
  messages: ChatMessage[];
  sending: boolean;
  loadingHistory: boolean;
  onChatLayout: (event: any) => void;
}

export function DogDetailsView({
  dog,
  email,
  onChat,
  onSendMessage,
  messages,
  sending,
  loadingHistory,
  onChatLayout,
}: DogDetailsViewProps) {
  const toast = useToast();
  const [bioExpanded, setBioExpanded] = useState(false);

  const strong = isStrongMatch(dog);
  const traits = dogTraits(dog);
  const bio = dogBio(dog);
  const idealHome = (dog.ideal_home || []).filter(Boolean);

  const openShelter = () => {
    if (dog.shelter_url) Linking.openURL(dog.shelter_url).catch(() => {});
    else if (dog.url) Linking.openURL(dog.url).catch(() => {});
    else toast.show('No shelter link available for this dog.');
  };

  const reportIssue = () => {
    const subject = encodeURIComponent(`ChattyHound issue: ${dog.name} (${dog.animal_id})`);
    const body = encodeURIComponent(
      `I noticed something wrong with this dog's listing:\n\n${dogShareUrl(dog.animal_id)}\n\n`
    );
    Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`).catch(() =>
      toast.show('Could not open mail app.')
    );
  };

  return (
    <View style={styles.body}>
      <Card>
        <SectionLabel>⚡ Quick Facts</SectionLabel>
        <QuickFacts dog={dog} />
      </Card>

      {traits.length > 0 && (
        <Card>
          <SectionLabel>🧠 Personality & Observations</SectionLabel>
          <View style={styles.traitWrap}>
            {traits.map((t, i) => (
              <Pill key={`${t}-${i}`} label={t} />
            ))}
          </View>
        </Card>
      )}

      {(idealHome.length > 0 || dog.people_notes) && (
        <View style={[styles.fitCard, { borderLeftColor: strong ? colors.teal : colors.amber }]}>
          <Text style={styles.fitTitle}>🏡 Ideal Home & Fit</Text>
          {idealHome.length > 0 ? (
            idealHome.map((item, i) => (
              <Text key={i} style={styles.fitItem}>
                • {item}
              </Text>
            ))
          ) : (
            <Text style={styles.fitItem}>{dog.people_notes}</Text>
          )}
        </View>
      )}

      {!!bio && (
        <Card>
          <SectionLabel>📖 Meet {dog.name}</SectionLabel>
          <Text style={styles.bioText}>
            {bioExpanded || bio.length <= 280 ? bio : `${bio.slice(0, 280).trim()}…`}
          </Text>
          {bio.length > 280 && (
            <Pressable onPress={() => setBioExpanded((v) => !v)} hitSlop={8}>
              <Text style={styles.seeMore}>{bioExpanded ? 'See less' : 'See more'}</Text>
            </Pressable>
          )}
        </Card>
      )}

      {/* CTA grid */}
      <View style={styles.ctaGrid}>
        <Pressable style={styles.ctaCard} onPress={openShelter} accessibilityRole="button">
          <ExternalLink size={18} color={colors.teal} />
          <Text style={styles.ctaTitle}>Official Shelter Page</Text>
          <Text style={styles.ctaSub}>View the live listing</Text>
        </Pressable>
        <Pressable
          style={[styles.ctaCard, styles.ctaPrimary]}
          onPress={onChat}
          accessibilityRole="button"
        >
          <MessageCircle size={18} color={colors.accentText} />
          <Text style={[styles.ctaTitle, styles.ctaTitlePrimary]}>Chat with {dog.name}</Text>
          <Text style={[styles.ctaSub, styles.ctaSubPrimary]}>Start with prompts</Text>
        </Pressable>
      </View>

      {/* Freshness + report */}
      <View style={styles.freshness}>
        <View style={styles.freshnessRow}>
          <CalendarClock size={15} color={colors.textFaint} />
          <Text style={styles.freshnessTitle}>
            Shelter listing last checked: {freshnessLabel(dog.info_refreshed_at)}
          </Text>
        </View>
        <Text style={styles.freshnessSub}>
          Availability changes quickly — confirm with the shelter.
        </Text>
        <View style={styles.divider} />
        <Pressable onPress={reportIssue} hitSlop={6} style={styles.reportRow}>
          <ShieldAlert size={14} color={colors.accent} />
          <Text style={styles.reportText}>Something wrong? Report an issue</Text>
        </Pressable>
      </View>

      {/* Inline Chat Panel */}
      <View onLayout={onChatLayout}>
        <InlineChat
          dog={dog}
          email={email}
          onSendMessage={onSendMessage}
          messages={messages}
          sending={sending}
          loadingHistory={loadingHistory}
        />
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  hero: {
    height: 320,
    width: '100%',
    backgroundColor: colors.slate800,
  },
  heroDesktop: {
    height: '100%',
  },
  heroImage: {
    ...StyleSheet.absoluteFillObject,
    width: '100%',
    height: '100%',
  },
  heroImageDesktop: {
    borderTopLeftRadius: 32,
    borderBottomLeftRadius: 32,
  },
  heroPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroPlaceholderText: {
    fontSize: 64,
  },
  heroOverlay: {
    ...StyleSheet.absoluteFillObject,
  },
  heroOverlayDesktop: {
    borderTopLeftRadius: 32,
    borderBottomLeftRadius: 32,
  },
  heroContent: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    padding: spacing.xl,
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  heroTextCol: {
    flex: 1,
  },
  dogName: {
    fontFamily: font.black,
    fontSize: 40,
    color: colors.white,
    letterSpacing: -1,
    marginTop: 6,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginTop: 2,
  },
  metaText: {
    fontFamily: font.bold,
    fontSize: 12.5,
    color: colors.textMuted,
    flexShrink: 1,
  },
  heroActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  shareBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(15,23,42,0.55)',
    borderWidth: 1,
    borderColor: colors.borderSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },

  body: {
    padding: spacing.xl,
    gap: spacing.md,
  },

  traitWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },

  fitCard: {
    backgroundColor: colors.tealBg,
    borderLeftWidth: 3.5,
    borderRadius: radius.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  fitTitle: {
    fontFamily: font.extrabold,
    fontSize: 13,
    color: colors.textMain,
    marginBottom: 6,
  },
  fitItem: {
    fontFamily: font.medium,
    fontSize: 13.5,
    lineHeight: 20,
    color: colors.textMuted,
  },

  bioText: {
    fontFamily: font.regular,
    fontSize: 14.5,
    lineHeight: 22,
    color: colors.textMuted,
  },
  seeMore: {
    fontFamily: font.extrabold,
    fontSize: 13,
    color: colors.accent,
    marginTop: 8,
  },

  ctaGrid: {
    flexDirection: 'row',
    gap: 10,
  },
  ctaCard: {
    flex: 1,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: colors.surfaceFaint,
    gap: 4,
  },
  ctaPrimary: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  ctaTitle: {
    fontFamily: font.black,
    fontSize: 13.5,
    color: colors.textMain,
    marginTop: 4,
  },
  ctaTitlePrimary: {
    color: colors.accentText,
  },
  ctaSub: {
    fontFamily: font.semibold,
    fontSize: 11.5,
    color: colors.textFaint,
  },
  ctaSubPrimary: {
    color: 'rgba(17,24,39,0.7)',
  },

  freshness: {
    backgroundColor: colors.surfaceFaint,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radius.sm,
    padding: spacing.md,
  },
  freshnessRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  freshnessTitle: {
    fontFamily: font.bold,
    fontSize: 12.5,
    color: colors.textMuted,
    flexShrink: 1,
  },
  freshnessSub: {
    fontFamily: font.regular,
    fontSize: 12,
    color: colors.textFaint,
    marginTop: 4,
  },
  divider: {
    height: 1,
    backgroundColor: colors.borderSoft,
    marginVertical: 10,
  },
  reportRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  reportText: {
    fontFamily: font.extrabold,
    fontSize: 12.5,
    color: colors.accent,
    textDecorationLine: 'underline',
  },
});
