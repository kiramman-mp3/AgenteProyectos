import { useLocalSearchParams } from 'expo-router';
import { useCallback } from 'react';

import { Badge, Body, Card, ErrorBox, Loading, Row, Screen, Section, Title, useLoader } from '@/components/ui';
import { api } from '@/lib/api';
import { fmtDate, severityColor, useTheme } from '@/lib/theme';

const CATEGORY: Record<string, string> = {
  error: 'Error potencial',
  duplicacion: 'Duplicación',
  mantenibilidad: 'Mantenibilidad',
  complejidad: 'Complejidad',
  seguridad: 'Seguridad',
  optimizacion: 'Optimización',
  buenas_practicas: 'Buenas prácticas',
};
const SEVERITY_ORDER = { critica: 0, alta: 1, media: 2, baja: 3 };

export default function CodeReviewDetail() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const loader = useCallback(() => api.codeReview(Number(id)), [id]);
  const { data: r, error } = useLoader(loader);

  if (!r && !error) return <Loading />;
  if (!r) return <Screen><ErrorBox message={error!} /></Screen>;

  const findings = [...r.findings].sort((a, b) => SEVERITY_ORDER[a.severidad] - SEVERITY_ORDER[b.severidad]);

  return (
    <Screen>
      <Card>
        <Title style={{ fontSize: 18 }}>Puntaje de calidad: {r.score}/100</Title>
        <Body>{r.summary}</Body>
        {r.review_notes ? <Body muted>Agente Revisor: {r.review_notes}</Body> : null}
      </Card>

      <Section>Commits analizados ({r.commits.length})</Section>
      {r.commits.map((c) => (
        <Body key={c.sha} muted>
          {c.sha} · {c.autor} · {fmtDate(c.fecha)} — {c.mensaje.split('\n')[0]}
        </Body>
      ))}

      <Section>Hallazgos ({findings.length})</Section>
      {findings.map((h, i) => (
        <Card key={i}>
          <Row>
            <Badge label={h.severidad} color={severityColor(t, h.severidad)} />
            <Badge label={CATEGORY[h.categoria] ?? h.categoria} color={t.neutral} />
          </Row>
          <Title style={{ fontFamily: 'monospace', fontSize: 13 }}>
            {h.archivo}{h.linea ? `:${h.linea}` : ''}
          </Title>
          <Body>{h.descripcion}</Body>
          <Body style={{ color: t.success }}>Recomendación: {h.recomendacion}</Body>
          {h.estandar_incumplido ? <Body muted>Estándar: {h.estandar_incumplido}</Body> : null}
          {h.comentario_revisor ? <Body muted>Revisor: {h.comentario_revisor}</Body> : null}
        </Card>
      ))}
    </Screen>
  );
}
