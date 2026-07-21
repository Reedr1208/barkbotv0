import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { ShieldCheck } from 'lucide-react-native';
import { useAuth } from '../auth';
import { colors, font, spacing } from '../theme';
import { Button } from './ui';

interface AboutModalProps {
  onClose: () => void;
}

export function AboutModal({ onClose }: AboutModalProps) {
  const router = useRouter();
  const { isLoggedIn } = useAuth();

  const handleSignIn = () => {
    onClose();
    router.push('/login');
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>🐾 Meet Adoptable Dogs</Text>
        </View>
        <Text style={styles.title}>Welcome to ChattyHound</Text>
      </View>

      <View style={styles.body}>
        <Text style={styles.highlightText}>
          Meet adoptable shelter dogs in a whole new way.
        </Text>
        
        <Text style={styles.paragraph}>
          Instead of just reading a generic profile, you can chat with each dog to get a feel for their personality,
          quirks, needs, and what makes them special. Ask about their favorite things, their ideal home, or what kind
          of human they’re hoping to find.
        </Text>
        
        <View style={styles.italicCard}>
          <Text style={styles.italicText}>
            Every chat is designed to help you move beyond facts and stats — and maybe meet your new best friend.
          </Text>
        </View>

        {!isLoggedIn && (
          <View style={styles.loginCallout}>
            <View style={styles.loginCalloutTextCol}>
              <Text style={styles.loginCalloutTitle}>🐾 Personalized Matches</Text>
              <Text style={styles.loginCalloutBody}>
                Sign in to save preferences and find matching dogs!
              </Text>
            </View>
            <Button
              label="Sign In"
              variant="teal"
              onPress={handleSignIn}
              style={styles.loginBtn}
              textStyle={styles.loginBtnText}
            />
          </View>
        )}

        <View style={styles.trustBanner}>
          <ShieldCheck size={18} color={colors.teal} />
          <Text style={styles.trustText}>
            ChattyHound is a playful AI companion. The official shelter page is always the authority
            for medical, behavioral, and adoption details.
          </Text>
        </View>
      </View>

      <View style={styles.footer}>
        <Button label="Start Sniffing 🐶" onPress={onClose} style={styles.cta} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.lg,
  },
  header: {
    alignItems: 'flex-start',
    gap: spacing.xs,
  },
  badge: {
    backgroundColor: 'rgba(20, 184, 166, 0.1)',
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 8,
  },
  badgeText: {
    fontFamily: font.bold,
    fontSize: 11,
    color: colors.teal,
    textTransform: 'uppercase',
  },
  title: {
    fontFamily: font.black,
    fontSize: 22,
    color: colors.textMain,
    letterSpacing: -0.5,
  },
  body: {
    gap: spacing.md,
  },
  highlightText: {
    fontFamily: font.extrabold,
    fontSize: 15,
    color: colors.accentHover,
    lineHeight: 22,
  },
  paragraph: {
    fontFamily: font.regular,
    fontSize: 13.5,
    lineHeight: 20,
    color: colors.textMuted,
  },
  italicCard: {
    backgroundColor: colors.creamBg,
    borderLeftWidth: 3,
    borderLeftColor: colors.accent,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 4,
  },
  italicText: {
    fontFamily: font.medium,
    fontSize: 13,
    fontStyle: 'italic',
    lineHeight: 18,
    color: colors.textMuted,
  },
  loginCallout: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    backgroundColor: 'rgba(20, 184, 166, 0.04)',
    borderWidth: 1,
    borderColor: 'rgba(20, 184, 166, 0.15)',
    borderRadius: 14,
    padding: spacing.md,
    marginTop: spacing.xs,
  },
  loginCalloutTextCol: {
    flex: 1,
  },
  loginCalloutTitle: {
    fontFamily: font.extrabold,
    fontSize: 13,
    color: colors.teal,
    marginBottom: 2,
  },
  loginCalloutBody: {
    fontFamily: font.medium,
    fontSize: 11.5,
    lineHeight: 15,
    color: colors.textMuted,
  },
  loginBtn: {
    paddingHorizontal: 12,
    minHeight: 32,
    borderRadius: 16,
  },
  loginBtnText: {
    fontSize: 11.5,
  },
  trustBanner: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
    backgroundColor: colors.tealBg,
    borderRadius: 8,
    padding: spacing.md,
    marginTop: spacing.xs,
  },
  trustText: {
    flex: 1,
    fontFamily: font.medium,
    fontSize: 12,
    lineHeight: 17,
    color: colors.textMuted,
  },
  footer: {
    marginTop: spacing.sm,
  },
  cta: {
    alignSelf: 'stretch',
  },
});
