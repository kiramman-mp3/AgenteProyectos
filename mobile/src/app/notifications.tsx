import { router } from 'expo-router';
import { useEffect } from 'react';

import { Badge, Body, Card, Empty, ErrorBox, Loading, Row, Screen, Title, useLoader } from '@/components/ui';
import { api, Notification } from '@/lib/api';
import { fmtDate, useTheme } from '@/lib/theme';

export default function NotificationsScreen() {
  const t = useTheme();
  const { data, error, refreshing, refresh } = useLoader(api.notifications);

  useEffect(() => {
    if (data?.some((n) => !n.read)) void api.readAllNotifications();
  }, [data]);

  const open = (n: Notification) => {
    if (!n.entity_id) return;
    if (n.entity === 'propuesta') router.push({ pathname: '/proposal/[id]', params: { id: n.entity_id } });
    if (n.entity === 'reporte') router.push({ pathname: '/report/[id]', params: { id: n.entity_id } });
    if (n.entity === 'revision_codigo') router.push({ pathname: '/code-review/[id]', params: { id: n.entity_id } });
  };
  const color = (l: string) => (l === 'critico' ? t.danger : l === 'advertencia' ? t.warning : t.info);

  if (!data && !error) return <Loading />;
  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      {error && <ErrorBox message={error} />}
      {data?.length === 0 && <Empty text="Sin notificaciones." />}
      {data?.map((n) => (
        <Card key={n.id} onPress={() => open(n)} style={!n.read ? { borderColor: color(n.level), borderWidth: 1 } : undefined}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Badge label={n.level} color={color(n.level)} />
            <Body muted>{fmtDate(n.created_at, true)}</Body>
          </Row>
          <Title>{n.title}</Title>
          {n.body ? <Body muted>{n.body}</Body> : null}
        </Card>
      ))}
    </Screen>
  );
}
