import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { Loading } from '@/components/ui';
import { AuthProvider, useAuth } from '@/lib/auth';
import { useTheme } from '@/lib/theme';

function RootStack() {
  const { session, loading } = useAuth();
  const t = useTheme();
  if (loading) return <Loading />;

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: t.card },
        headerTintColor: t.text,
        contentStyle: { backgroundColor: t.bg },
      }}
    >
      <Stack.Protected guard={!session}>
        <Stack.Screen name="login" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={!!session && !!session.must_change_password}>
        <Stack.Screen name="change-password" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={!!session && !session.must_change_password}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="proposal/[id]" options={{ title: 'Propuesta' }} />
        <Stack.Screen name="report/[id]" options={{ title: 'Reporte semanal' }} />
        <Stack.Screen name="code-review/[id]" options={{ title: 'Revisión de código' }} />
        <Stack.Screen name="audit" options={{ title: 'Bitácora de auditoría' }} />
        <Stack.Screen name="notifications" options={{ title: 'Notificaciones' }} />
        <Stack.Screen name="account" options={{ title: 'Mi cuenta' }} />
        <Stack.Screen name="users" options={{ title: 'Usuarios' }} />
        <Stack.Screen name="user/[id]" options={{ title: 'Usuario' }} />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="auto" />
      <RootStack />
    </AuthProvider>
  );
}
