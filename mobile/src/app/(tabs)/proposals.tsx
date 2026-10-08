import { router } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Badge, Body, Card, Empty, ErrorBox, Loading, Row, Screen, Title, useLoader } from '@/components/ui';
import { api } from '@/lib/api';
import { ACTION_LABEL, fmtDate, PROPOSAL_STATUS_LABEL, proposalColor, useTheme } from '@/lib/theme';

const TABS = [
  { key: 'pendiente_gestor', label: 'Pendientes' },
  { key: '', label: 'Todas' },
] as const;

export default function ProposalsScreen() {
  const t = useTheme();
  const [tab, setTab] = useState<string>('pendiente_gestor');
  const loader = useCallback(() => api.proposals(tab || undefined), [tab]);
  const { data, error, refreshing, refresh } = useLoader(loader);

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <View style={{ flexDirection: 'row', borderRadius: 10, borderWidth: 1, borderColor: t.border, overflow: 'hidden' }}>
        {TABS.map((x) => (
          <Pressable
            key={x.key}
            onPress={() => setTab(x.key)}
            style={{ flex: 1, padding: 10, alignItems: 'center', backgroundColor: tab === x.key ? t.primary : t.card }}
          >
            <Text style={{ color: tab === x.key ? t.primaryText : t.text, fontWeight: '600' }}>{x.label}</Text>
          </Pressable>
        ))}
      </View>
      {error && <ErrorBox message={error} />}
      {!data && !error && <Loading />}
      {data?.length === 0 && (
        <Empty text={tab ? 'No hay propuestas esperando tu decisión.' : 'Todavía no hay propuestas.'} />
      )}
      {data?.map((p) => (
        <Card key={p.id} onPress={() => router.push({ pathname: '/proposal/[id]', params: { id: String(p.id) } })}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Badge label={PROPOSAL_STATUS_LABEL[p.status] ?? p.status} color={proposalColor(t, p.status)} />
            <Body muted>#{p.id} · {fmtDate(p.created_at, true)}</Body>
          </Row>
          <Title>
            {ACTION_LABEL[p.action_type] ?? p.action_type}: {p.target_name ?? 'repositorio'}
          </Title>
          {p.problem ? <Body muted>{p.problem}</Body> : null}
          {p.approver_risk && <Body muted>Riesgo evaluado: {p.approver_risk}</Body>}
        </Card>
      ))}
    </Screen>
  );
}
