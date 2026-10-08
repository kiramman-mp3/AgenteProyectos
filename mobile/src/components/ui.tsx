import { useFocusEffect } from 'expo-router';
import { ReactNode, useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';

import { useTheme } from '@/lib/theme';

/** Carga datos al enfocar la pantalla y permite refrescar con gesto. */
export function useLoader<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await fn());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [fn]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const refresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  return { data, error, refreshing, refresh, reload: load };
}

export function Screen({
  children,
  refreshing,
  onRefresh,
}: {
  children: ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
}) {
  const t = useTheme();
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: t.bg }}
      contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 32 }}
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} /> : undefined}
    >
      {children}
    </ScrollView>
  );
}

export function Card({ children, style, onPress }: { children: ReactNode; style?: ViewStyle; onPress?: () => void }) {
  const t = useTheme();
  const base = [styles.card, { backgroundColor: t.card, borderColor: t.border }, style];
  if (!onPress) return <View style={base}>{children}</View>;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [...base, pressed && { opacity: 0.7 }]}>
      {children}
    </Pressable>
  );
}

export function Title({ children, style }: { children: ReactNode; style?: TextStyle }) {
  const t = useTheme();
  return <Text style={[{ color: t.text, fontSize: 16, fontWeight: '600' }, style]}>{children}</Text>;
}

export function Body({ children, muted, style }: { children: ReactNode; muted?: boolean; style?: TextStyle }) {
  const t = useTheme();
  return <Text style={[{ color: muted ? t.muted : t.text, fontSize: 14, lineHeight: 20 }, style]}>{children}</Text>;
}

export function Section({ children }: { children: ReactNode }) {
  const t = useTheme();
  return (
    <Text style={{ color: t.muted, fontSize: 12, fontWeight: '700', letterSpacing: 0.6, marginTop: 8 }}>
      {(Array.isArray(children) ? children.join('') : String(children)).toUpperCase()}
    </Text>
  );
}

export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={{ color, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}

export function ProgressBar({ value, color }: { value: number; color?: string }) {
  const t = useTheme();
  const pct = Math.max(0, Math.min(100, value));
  return (
    <View style={[styles.track, { backgroundColor: t.track }]}>
      <View style={{ width: `${pct}%`, height: '100%', borderRadius: 4, backgroundColor: color ?? t.primary }} />
    </View>
  );
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  loading?: boolean;
}) {
  const t = useTheme();
  const bg = variant === 'primary' ? t.primary : variant === 'danger' ? t.danger : 'transparent';
  const fg = variant === 'secondary' ? t.primary : t.primaryText;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, borderColor: variant === 'secondary' ? t.primary : bg },
        (pressed || disabled) && { opacity: 0.6 },
      ]}
    >
      {loading ? <ActivityIndicator color={fg} /> : <Text style={{ color: fg, fontWeight: '600' }}>{label}</Text>}
    </Pressable>
  );
}

export function ErrorBox({ message }: { message: string }) {
  const t = useTheme();
  return (
    <Card style={{ borderColor: t.danger }}>
      <Body style={{ color: t.danger }}>{message}</Body>
    </Card>
  );
}

export function Empty({ text }: { text: string }) {
  return (
    <Card style={{ alignItems: 'center', paddingVertical: 24 }}>
      <Body muted>{text}</Body>
    </Card>
  );
}

export function Loading() {
  const t = useTheme();
  return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: t.bg }}>
      <ActivityIndicator size="large" color={t.primary} />
    </View>
  );
}

export function Row({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: { borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, padding: 14, gap: 6 },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 2,
    alignSelf: 'flex-start',
  },
  dot: { width: 7, height: 7, borderRadius: 4 },
  track: { height: 8, borderRadius: 4, overflow: 'hidden', width: '100%' },
  button: {
    flex: 1,
    minHeight: 44,
    borderRadius: 10,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
});
