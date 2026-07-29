import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useAuth } from '../src/auth';
import { colors } from '../src/theme';

/**
 * Entry gate: send first-time users through the welcome screen, otherwise
 * straight into the Discover tab. Keeps the "landing first" behavior of the web.
 */
export default function Index() {
  const { ready, visited, isLoggedIn } = useAuth();

  if (!ready) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.slate950 }}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  if (visited || isLoggedIn) return <Redirect href="/discover" />;
  return <Redirect href="/welcome" />;
}
