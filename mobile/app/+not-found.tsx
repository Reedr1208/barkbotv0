import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Link, Stack } from 'expo-router';
import { colors, font } from '../src/theme';
import { EmptyState } from '../src/components/common';

export default function NotFound() {
  return (
    <>
      <Stack.Screen options={{ title: 'Not found' }} />
      <View style={styles.screen}>
        <EmptyState
          icon="🐾"
          title="Page not found"
          description="We couldn't find what you were looking for."
        />
        <Link href="/discover" style={styles.link}>
          <Text style={styles.linkText}>Go to Discover</Text>
        </Link>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.slate950, alignItems: 'center', justifyContent: 'center' },
  link: { marginTop: 8 },
  linkText: { fontFamily: font.extrabold, fontSize: 15, color: colors.accent },
});
