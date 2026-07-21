import React, { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { colors } from '../../src/theme';

/**
 * Redirect gate for shared links: chattyhound.com/dogs/:id and
 * chattyhound.com/dogs/:location/:id. Resolves client-side to /discover?animal_id=:id.
 */
export default function DogDetail() {
  const router = useRouter();
  const { slug } = useLocalSearchParams<{ slug: string | string[] }>();

  const segments = Array.isArray(slug) ? slug : String(slug ?? '').split('/').filter(Boolean);
  const animalId = segments.length ? segments[segments.length - 1] : '';

  useEffect(() => {
    if (animalId && animalId !== 'alldogs') {
      router.replace({
        pathname: '/discover',
        params: { animal_id: animalId }
      });
    } else {
      router.replace('/discover');
    }
  }, [animalId]);

  return (
    <View style={styles.screen}>
      <ActivityIndicator color={colors.accent} size="large" />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.slate950,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
