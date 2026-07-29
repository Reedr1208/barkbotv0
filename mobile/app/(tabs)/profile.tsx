import React, { useEffect, useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Picker } from '@react-native-picker/picker';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LogOut, ShieldCheck, Trash2 } from 'lucide-react-native';
import { api, AgeGroup, Gender, LocationOption, Size } from '../../src/api';
import { useAuth } from '../../src/auth';
import { useToast } from '../../src/toast';
import { colors, font, radius, spacing } from '../../src/theme';
import { Button, Card, SectionLabel } from '../../src/components/ui';
import { SegmentedField } from '../../src/components/common';

const GENDER_OPTS = [
  { label: 'Any', value: 'any' as Gender },
  { label: 'Male ♂️', value: 'male' as Gender },
  { label: 'Female ♀️', value: 'female' as Gender },
];
const AGE_OPTS = [
  { label: 'Any', value: 'any' as AgeGroup },
  { label: 'Puppy', value: 'puppy' as AgeGroup },
  { label: 'Young', value: 'young' as AgeGroup },
  { label: 'Adult', value: 'adult' as AgeGroup },
  { label: 'Senior', value: 'senior' as AgeGroup },
];
const SIZE_OPTS = [
  { label: 'Any', value: 'any' as Size },
  { label: 'Small', value: 'small' as Size },
  { label: 'Medium', value: 'medium' as Size },
  { label: 'Large', value: 'large' as Size },
];

export default function Profile() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const { email, isLoggedIn, preferences, savePreferences, signOut, deleteAccount } = useAuth();
  const [locations, setLocations] = useState<LocationOption[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .locations()
      .then(({ locations }) => {
        if (!cancelled) setLocations(locations || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const onSignOut = async () => {
    await signOut();
    toast.show('Signed out');
  };

  const confirmDelete = () => {
    const title = isLoggedIn ? 'Delete account & data?' : 'Clear data on this device?';
    const message = isLoggedIn
      ? 'This permanently deletes your preferences, saved dogs, and chat history from our servers. This cannot be undone.'
      : 'This clears your saved dogs and preferences stored on this device.';
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteAccount();
            toast.show('🗑️ Your data was deleted');
            router.replace('/discover');
          } catch {
            toast.show('Could not delete your data. Please try again.');
          }
        },
      },
    ]);
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}>
      <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
        <Text style={styles.title}>Match Profile</Text>
        <Text style={styles.subtitle}>
          Tell us what you're looking for and we'll prioritize dogs who fit. Leave anything as
          “Any” to keep matches broad.
        </Text>
      </View>

      <View style={styles.body}>
        {/* Account card */}
        {isLoggedIn ? (
          <Card style={styles.account}>
            <View style={{ flex: 1 }}>
              <Text style={styles.accountLabel}>Signed in as</Text>
              <Text style={styles.accountEmail} numberOfLines={1}>
                {email}
              </Text>
            </View>
            <Pressable onPress={onSignOut} style={styles.signOut} hitSlop={6}>
              <LogOut size={16} color={colors.textMuted} />
              <Text style={styles.signOutText}>Sign Out</Text>
            </Pressable>
          </Card>
        ) : (
          <View style={styles.signInCard}>
            <Text style={styles.signInTitle}>🐾 Save your matches</Text>
            <Text style={styles.signInBody}>
              Sign in with your email to save preferences, favorites, and chats across devices.
            </Text>
            <Button label="Sign In & Save" variant="teal" onPress={() => router.push('/login')} />
          </View>
        )}

        {/* Preferences */}
        <Card>
          <SectionLabel>🐕 Basics</SectionLabel>
          <SegmentedField
            label="Dog gender"
            options={GENDER_OPTS}
            value={preferences.gender}
            onChange={(v) => savePreferences({ gender: v })}
          />
          <SegmentedField
            label="Age category"
            options={AGE_OPTS}
            value={preferences.age_group}
            onChange={(v) => savePreferences({ age_group: v })}
          />
          <SegmentedField
            label="Weight class"
            options={SIZE_OPTS}
            value={preferences.size}
            onChange={(v) => savePreferences({ size: v })}
          />

          <Text style={styles.fieldLabel}>Preferred area</Text>
          <View style={styles.pickerWrap}>
            <Picker
              selectedValue={preferences.location}
              onValueChange={(v) => savePreferences({ location: String(v) })}
              dropdownIconColor={colors.textMuted}
              style={styles.picker}
              itemStyle={Platform.OS === 'ios' ? styles.pickerItem : undefined}
            >
              <Picker.Item label="All Locations 🌎" value="any" color={Platform.OS === 'ios' ? colors.textMain : undefined} />
              {locations.map((loc) => (
                <Picker.Item
                  key={loc.relative_path || loc.display_name}
                  label={loc.display_name}
                  value={loc.display_name}
                  color={Platform.OS === 'ios' ? colors.textMain : undefined}
                />
              ))}
            </Picker>
          </View>
        </Card>

        {/* About */}
        <Card>
          <SectionLabel>About ChattyHound</SectionLabel>
          <Text style={styles.aboutText}>
            Instead of reading a generic profile, you can chat with each dog to get a feel for their
            personality, quirks, and what makes them special. Every chat is designed to help you move
            beyond facts and stats — and maybe meet your new best friend.
          </Text>
          <View style={styles.trust}>
            <ShieldCheck size={16} color={colors.teal} />
            <Text style={styles.trustText}>
              ChattyHound is a playful AI companion. The official shelter page is always the authority
              for medical, behavioral, and adoption details.
            </Text>
          </View>
        </Card>

        {/* Danger zone */}
        <Card>
          <SectionLabel>Account</SectionLabel>
          <Text style={styles.dangerText}>
            {isLoggedIn
              ? 'Permanently delete your account and all associated data (preferences, saved dogs, and chats).'
              : 'Clear the saved dogs and preferences stored on this device.'}
          </Text>
          <View style={styles.dangerBtnRow}>
            <Trash2 size={16} color={colors.danger} />
            <Button
              label={isLoggedIn ? 'Delete my account & data' : 'Clear local data'}
              variant="danger"
              onPress={confirmDelete}
              style={styles.dangerBtn}
            />
          </View>
        </Card>
      </View>
    </ScrollView>
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
  subtitle: { fontFamily: font.medium, fontSize: 13, lineHeight: 19, color: colors.textMuted, marginTop: 4 },
  body: { padding: spacing.xl, gap: spacing.md },
  account: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  accountLabel: { fontFamily: font.semibold, fontSize: 11.5, color: colors.textFaint, textTransform: 'uppercase', letterSpacing: 0.4 },
  accountEmail: { fontFamily: font.extrabold, fontSize: 15.5, color: colors.textMain, marginTop: 2 },
  signOut: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  signOutText: { fontFamily: font.bold, fontSize: 13, color: colors.textMuted },
  signInCard: {
    backgroundColor: colors.tealBg,
    borderWidth: 1.5,
    borderColor: colors.tealBorder,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  signInTitle: { fontFamily: font.black, fontSize: 16, color: colors.textMain },
  signInBody: { fontFamily: font.medium, fontSize: 13.5, lineHeight: 20, color: colors.textMuted, marginBottom: 4 },
  fieldLabel: {
    fontFamily: font.extrabold,
    fontSize: 12.5,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    color: colors.textFaint,
    marginBottom: spacing.sm,
  },
  pickerWrap: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  picker: { color: colors.textMain },
  pickerItem: { color: colors.textMain, fontSize: 16 },
  aboutText: { fontFamily: font.regular, fontSize: 14, lineHeight: 21, color: colors.textMuted },
  trust: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
    marginTop: spacing.md,
    backgroundColor: colors.tealBg,
    borderRadius: radius.sm,
    padding: spacing.md,
  },
  trustText: { flex: 1, fontFamily: font.medium, fontSize: 12.5, lineHeight: 18, color: colors.textMuted },
  dangerText: { fontFamily: font.regular, fontSize: 13, lineHeight: 19, color: colors.textMuted, marginBottom: spacing.md },
  dangerBtnRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  dangerBtn: { flex: 1 },
});
