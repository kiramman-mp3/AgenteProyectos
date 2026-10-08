import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { Body, Button, Card, Empty, ErrorBox, Loading, Row, Screen, Title, useLoader } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { fmtDate } from '@/lib/theme';

export default function ReportsScreen() {
  const { canDecide } = useAuth();
  const { data, error, refreshing, refresh } = useLoader(api.reports);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    try {
      await api.generateReport();
      Alert.alert('Generando reporte', 'Estará disponible en uno o dos minutos. Desliza hacia abajo para actualizar.');
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!data && !error) return <Loading />;
  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      {canDecide && (
        <Row>
          <Button label="Generar reporte ahora" onPress={generate} loading={busy} />
        </Row>
      )}
      {error && <ErrorBox message={error} />}
      {data?.length === 0 && <Empty text="El reporte semanal se genera automáticamente cada semana." />}
      {data?.map((r) => (
        <Card key={r.id} onPress={() => router.push({ pathname: '/report/[id]', params: { id: String(r.id) } })}>
          <Title>
            Semana {fmtDate(r.period_start)} – {fmtDate(r.period_end)}
          </Title>
          <Body muted>Generado el {fmtDate(r.created_at, true)}</Body>
        </Card>
      ))}
    </Screen>
  );
}
