import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import { ColorValue } from 'react-native';
import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import { useTheme } from '@/lib/theme';

type IconName = keyof typeof Ionicons.glyphMap;
const icon =
  (name: IconName) =>
  ({ color, size }: { color: ColorValue; size: number }) => <Ionicons name={name} color={color} size={size} />;

export default function TabsLayout() {
  const t = useTheme();
  const [pending, setPending] = useState(0);

  // Actualiza el contador de decisiones pendientes cada minuto.
  useEffect(() => {
    const tick = () => api.dashboard().then((d) => setPending(d.pending_decisions)).catch(() => {});
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: t.primary,
        tabBarInactiveTintColor: t.muted,
        tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border },
        headerStyle: { backgroundColor: t.card },
        headerTintColor: t.text,
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Panel', tabBarIcon: icon('speedometer-outline') }} />
      <Tabs.Screen name="activities" options={{ title: 'Actividades', tabBarIcon: icon('list-outline') }} />
      <Tabs.Screen
        name="proposals"
        options={{
          title: 'Propuestas',
          tabBarIcon: icon('checkmark-done-outline'),
          tabBarBadge: pending > 0 ? pending : undefined,
        }}
      />
      <Tabs.Screen name="code" options={{ title: 'Código', tabBarIcon: icon('code-slash-outline') }} />
      <Tabs.Screen name="reports" options={{ title: 'Reportes', tabBarIcon: icon('document-text-outline') }} />
    </Tabs>
  );
}
