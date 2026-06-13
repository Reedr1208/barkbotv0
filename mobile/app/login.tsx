import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { X } from 'lucide-react-native';
import { useAuth } from '../src/auth';
import { colors, font, radius, spacing } from '../src/theme';
import { Button } from '../src/components/ui';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { login, markVisited } = useAuth();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const close = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/discover');
  };

  const submit = async () => {
    const value = email.trim().toLowerCase();
    if (!EMAIL_RE.test(value)) {
      setError('Please enter a valid email address.');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await login(value);
      markVisited();
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not sign in. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const continueAsGuest = () => {
    markVisited();
    close();
  };

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={[styles.sheet, { paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.xl }]}>
        <Pressable onPress={close} style={styles.close} hitSlop={8} accessibilityLabel="Close">
          <X size={22} color={colors.textMuted} />
        </Pressable>

        <Text style={styles.badge}>🐾 BUILD YOUR DOG MATCH PROFILE</Text>
        <Text style={styles.title}>Sign in to ChattyHound</Text>
        <Text style={styles.subtitle}>
          Save your preferences, favorites, and chats so we can prioritize dogs who fit your life.
          No password needed — just your email.
        </Text>

        <Text style={styles.label}>Email address</Text>
        <TextInput
          style={[styles.input, error && styles.inputError]}
          value={email}
          onChangeText={(t) => {
            setEmail(t);
            if (error) setError(null);
          }}
          placeholder="e.g. barker@gmail.com"
          placeholderTextColor={colors.textFaint}
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          returnKeyType="go"
          onSubmitEditing={submit}
          editable={!busy}
        />
        {!!error && <Text style={styles.error}>{error}</Text>}

        <Text style={styles.privacy}>
          🔒 Your email is only used to save your preferences. We never share your data.
        </Text>

        <Button label="Sign In & Save" onPress={submit} loading={busy} style={styles.submit} />
        <Button label="Continue as guest" variant="ghost" onPress={continueAsGuest} disabled={busy} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.slate950 },
  sheet: { flex: 1, paddingHorizontal: spacing.xl },
  close: { alignSelf: 'flex-end', padding: 4, marginBottom: spacing.sm },
  badge: { fontFamily: font.black, fontSize: 11, letterSpacing: 1.5, color: colors.accent },
  title: { fontFamily: font.black, fontSize: 28, color: colors.textMain, marginTop: 8, letterSpacing: -0.5 },
  subtitle: { fontFamily: font.medium, fontSize: 14.5, lineHeight: 22, color: colors.textMuted, marginTop: 8 },
  label: {
    fontFamily: font.extrabold,
    fontSize: 12,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    color: colors.textFaint,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
  },
  input: {
    height: 52,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    borderWidth: 1.5,
    borderColor: colors.borderSoft,
    paddingHorizontal: spacing.lg,
    color: colors.textMain,
    fontFamily: font.semibold,
    fontSize: 16,
  },
  inputError: { borderColor: colors.danger },
  error: { fontFamily: font.bold, fontSize: 13, color: colors.danger, marginTop: 8 },
  privacy: { fontFamily: font.regular, fontSize: 12.5, lineHeight: 18, color: colors.textFaint, marginTop: spacing.md },
  submit: { alignSelf: 'stretch', marginTop: spacing.xl },
});
