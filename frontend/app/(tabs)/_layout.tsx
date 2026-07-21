import React from 'react';
import { Tabs } from 'expo-router';
import { Heart, PawPrint, SlidersHorizontal } from 'lucide-react-native';
import { colors, font } from '../../src/theme';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.textFaint,
        tabBarStyle: {
          display: 'none',
          backgroundColor: 'rgba(2,6,23,0.96)',
          borderTopColor: colors.borderSoft,
          borderTopWidth: 1,
          height: 64,
          paddingTop: 6,
          paddingBottom: 10,
        },
        tabBarLabelStyle: { fontFamily: font.bold, fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="discover"
        options={{
          title: 'Discover',
          tabBarIcon: ({ color, size }) => <PawPrint color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="my-dogs"
        options={{
          title: 'My Dogs',
          tabBarIcon: ({ color, size }) => <Heart color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color, size }) => <SlidersHorizontal color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
