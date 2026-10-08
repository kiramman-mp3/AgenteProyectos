import { Linking } from 'react-native';

import { Activity } from '@/lib/api';
import { fmtDate, STATUS_LABEL, statusColor, useTheme } from '@/lib/theme';

import { Badge, Body, Card, ProgressBar, Row, Title } from './ui';

export function ActivityCard({ activity: a }: { activity: Activity }) {
  const t = useTheme();
  const color = statusColor(t, a.status);
  return (
    <Card onPress={a.url ? () => Linking.openURL(a.url) : undefined}>
      <Row style={{ justifyContent: 'space-between' }}>
        <Badge label={STATUS_LABEL[a.status]} color={color} />
        {a.at_risk && a.status !== 'retrasada' && <Badge label="En riesgo" color={t.warning} />}
        {a.priority && <Badge label={`Prioridad ${a.priority}`} color={t.neutral} />}
      </Row>
      <Title>{a.name}</Title>
      <Body muted>
        {a.list} · {a.responsables.length ? a.responsables.join(', ') : 'Sin responsable'}
      </Body>
      <Body muted>
        Inicio: {fmtDate(a.start)} · Límite: {fmtDate(a.due)}
      </Body>
      <ProgressBar value={a.progress * 100} color={color} />
      {a.risk_reasons.length > 0 && <Body style={{ color: t.warning }}>⚠ {a.risk_reasons.join(' · ')}</Body>}
      {a.blocks.length > 0 && a.status !== 'completada' && (
        <Body muted>Impacta a {a.blocks.length} actividad(es) dependiente(s)</Body>
      )}
    </Card>
  );
}
