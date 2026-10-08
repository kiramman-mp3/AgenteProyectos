import { useState } from 'react';
import { Pressable, ScrollView, Text } from 'react-native';

import { ActivityCard } from '@/components/ActivityCard';
import { Empty, ErrorBox, Loading, Screen, useLoader } from '@/components/ui';
import { api } from '@/lib/api';
import { STATUS_LABEL, statusColor, useTheme } from '@/lib/theme';

const FILTERS = ['todas', 'retrasada', 'bloqueada', 'en_ejecucion', 'pendiente', 'completada', 'riesgo'] as const;

export default function ActivitiesScreen() {
  const t = useTheme();
  const { data, error, refreshing, refresh } = useLoader(api.activities);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('todas');

  if (!data && !error) return <Loading />;
  const items = (data ?? []).filter((a) =>
    filter === 'todas' ? true : filter === 'riesgo' ? a.at_risk : a.status === filter,
  );

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {FILTERS.map((f) => {
          const active = f === filter;
          const color = f === 'todas' ? t.primary : f === 'riesgo' ? t.warning : statusColor(t, f);
          const count = (data ?? []).filter((a) =>
            f === 'todas' ? true : f === 'riesgo' ? a.at_risk : a.status === f,
          ).length;
          return (
            <Pressable
              key={f}
              onPress={() => setFilter(f)}
              style={{
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1,
                borderColor: color, backgroundColor: active ? color : 'transparent',
              }}
            >
              <Text style={{ color: active ? t.card : color, fontWeight: '600', fontSize: 13 }}>
                {f === 'todas' ? 'Todas' : f === 'riesgo' ? 'En riesgo' : STATUS_LABEL[f]} ({count})
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      {error && <ErrorBox message={error} />}
      {items.length === 0 && <Empty text="No hay actividades con este filtro." />}
      {items.map((a) => (
        <ActivityCard key={a.id} activity={a} />
      ))}
    </Screen>
  );
}
