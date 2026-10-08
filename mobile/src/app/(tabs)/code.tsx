import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { Badge, Body, Button, Card, Empty, ErrorBox, Loading, Row, Screen, Title, useLoader } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { fmtDate, useTheme } from '@/lib/theme';

export default function CodeScreen() {
  const t = useTheme();
  const { canDecide } = useAuth();
  const { data, error, refreshing, refresh } = useLoader(api.codeReviews);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      await api.runCodeReview();
      Alert.alert('Revisión iniciada', 'El Agente Ejecutor analiza los últimos commits y el Revisor valida los hallazgos.');
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!data && !error) return <Loading />;
  const scoreColor = (s: number) => (s >= 80 ? t.success : s >= 60 ? t.warning : t.danger);

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Card>
        <Body muted>
          El agente analiza los cambios del repositorio y genera recomendaciones. Nunca modifica el código: los
          hallazgos graves se proponen como issues de GitHub que tú debes aprobar.
        </Body>
      </Card>
      {canDecide && (
        <Row>
          <Button label="Revisar cambios ahora" onPress={run} loading={busy} />
        </Row>
      )}
      {error && <ErrorBox message={error} />}
      {data?.length === 0 && <Empty text="Todavía no hay revisiones de código." />}
      {data?.map((r) => (
        <Card key={r.id} onPress={() => router.push({ pathname: '/code-review/[id]', params: { id: String(r.id) } })}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Badge label={`Calidad ${r.score}/100`} color={scoreColor(r.score)} />
            <Body muted>{fmtDate(r.created_at, true)}</Body>
          </Row>
          <Title>
            {r.repo} · {r.commit_from.slice(0, 7)}…{r.commit_to.slice(0, 7)}
          </Title>
          <Body muted>
            {r.findings_count} hallazgos{r.severe_count ? ` · ${r.severe_count} graves` : ''}
          </Body>
        </Card>
      ))}
    </Screen>
  );
}
