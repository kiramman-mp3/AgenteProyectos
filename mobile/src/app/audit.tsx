import { useCallback, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Badge, Body, Card, ErrorBox, Loading, Row, Screen, Title, useLoader } from '@/components/ui';
import { api, AuditEntry } from '@/lib/api';
import { fmtDate, useTheme } from '@/lib/theme';

const FILTERS = [
  { key: '', label: 'Todos' },
  { key: 'agente', label: 'Agentes' },
  { key: 'humano', label: 'Personas' },
  { key: 'sistema', label: 'Sistema' },
];

function details(d: Record<string, unknown>): string {
  return Object.entries(d)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join('\n')
    .slice(0, 400);
}

export default function AuditScreen() {
  const t = useTheme();
  const [filter, setFilter] = useState('');
  const loader = useCallback(() => api.audit(filter || undefined), [filter]);
  const { data, error, refreshing, refresh } = useLoader(loader);

  const color = (e: AuditEntry) =>
    e.actor_type === 'humano' ? t.success : e.actor_type === 'agente' ? t.info : t.neutral;

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {FILTERS.map((f) => (
          <Pressable
            key={f.key}
            onPress={() => setFilter(f.key)}
            style={{
              paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: t.primary,
              backgroundColor: filter === f.key ? t.primary : 'transparent',
            }}
          >
            <Text style={{ color: filter === f.key ? t.primaryText : t.primary, fontWeight: '600' }}>{f.label}</Text>
          </Pressable>
        ))}
      </View>
      {error && <ErrorBox message={error} />}
      {!data && !error && <Loading />}
      {data?.map((e) => (
        <Card key={e.id}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Badge label={e.actor} color={color(e)} />
            <Body muted>{fmtDate(e.ts, true)}</Body>
          </Row>
          <Title>{e.action.replace(/_/g, ' ')}</Title>
          {e.entity && <Body muted>{e.entity}{e.entity_id ? ` #${e.entity_id.slice(0, 24)}` : ''}</Body>}
          {Object.keys(e.details).length > 0 && <Body muted>{details(e.details)}</Body>}
        </Card>
      ))}
    </Screen>
  );
}
