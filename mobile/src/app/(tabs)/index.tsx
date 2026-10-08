import Ionicons from '@expo/vector-icons/Ionicons';
import { router, useNavigation } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Alert, Linking, Pressable, Text, View } from 'react-native';

import { ActivityCard } from '@/components/ActivityCard';
import { Badge, Body, Button, Card, ErrorBox, Loading, ProgressBar, Row, Screen, Section, Title, useLoader } from '@/components/ui';
import { api, ActivityStatus } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { fmtDate, STATUS_LABEL, statusColor, useTheme } from '@/lib/theme';

const ORDER: ActivityStatus[] = ['completada', 'en_ejecucion', 'pendiente', 'retrasada', 'bloqueada'];

export default function DashboardScreen() {
  const t = useTheme();
  const navigation = useNavigation();
  const { session, logout, canDecide } = useAuth();
  const { data, error, refreshing, refresh } = useLoader(api.dashboard);
  const [busy, setBusy] = useState<string | null>(null);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={{ flexDirection: 'row', gap: 18, marginRight: 16 }}>
          <Pressable onPress={() => router.push('/notifications')} hitSlop={8}>
            <Ionicons name="notifications-outline" size={22} color={t.text} />
            {!!data?.unread_notifications && (
              <View
                style={{
                  position: 'absolute', right: -6, top: -4, backgroundColor: t.danger,
                  borderRadius: 8, minWidth: 16, paddingHorizontal: 3, alignItems: 'center',
                }}
              >
                <Text style={{ color: '#fff', fontSize: 10, fontWeight: '700' }}>{data.unread_notifications}</Text>
              </View>
            )}
          </Pressable>
          <Pressable onPress={() => router.push('/audit')} hitSlop={8}>
            <Ionicons name="time-outline" size={22} color={t.text} />
          </Pressable>
          <Pressable
            hitSlop={8}
            onPress={() =>
              Alert.alert('Cerrar sesión', `¿Salir como ${session?.username}?`, [
                { text: 'Cancelar', style: 'cancel' },
                { text: 'Salir', style: 'destructive', onPress: () => void logout() },
              ])
            }
          >
            <Ionicons name="log-out-outline" size={22} color={t.text} />
          </Pressable>
        </View>
      ),
    });
  }, [navigation, data?.unread_notifications, t, session, logout]);

  const run = async (key: string, fn: () => Promise<unknown>, message: string) => {
    setBusy(key);
    try {
      await fn();
      Alert.alert('Listo', message);
      await refresh();
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!data && !error) return <Loading />;
  const s = data?.summary;
  const missing = Object.entries(data?.credentials ?? {}).filter(([, ok]) => !ok).map(([k]) => k);

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      {error && <ErrorBox message={error} />}
      {missing.length > 0 && <ErrorBox message={`Faltan credenciales en el servidor: ${missing.join(', ')}`} />}

      {data && (
        <Card onPress={data.board.url ? () => Linking.openURL(data.board.url!) : undefined}>
          <Body muted>Tablero</Body>
          <Title style={{ fontSize: 20 }}>{data.board.name ?? 'Sin sincronizar'}</Title>
          <Body muted>Última sincronización: {fmtDate(data.last_sync, true)}</Body>
        </Card>
      )}

      {s ? (
        <Card>
          <Row style={{ justifyContent: 'space-between' }}>
            <Title>Avance general</Title>
            <Text style={{ color: t.text, fontSize: 28, fontWeight: '700' }}>{s.progress_weighted}%</Text>
          </Row>
          <ProgressBar value={s.progress_weighted} />
          <Body muted>
            {s.counts.completada} de {s.total} actividades completadas ({s.progress_completed}%)
          </Body>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
            {ORDER.map((st) => (
              <View
                key={st}
                style={{
                  flexGrow: 1, minWidth: '28%', borderRadius: 10, padding: 10,
                  borderWidth: 1, borderColor: t.border,
                }}
              >
                <Text style={{ color: statusColor(t, st), fontSize: 22, fontWeight: '700' }}>{s.counts[st]}</Text>
                <Text style={{ color: t.muted, fontSize: 12 }}>{STATUS_LABEL[st]}</Text>
              </View>
            ))}
          </View>
        </Card>
      ) : (
        data && <Body muted>Aún no hay datos. Sincroniza con Trello para empezar.</Body>
      )}

      {data && data.pending_decisions > 0 && (
        <Card onPress={() => router.push('/proposals')} style={{ borderColor: t.warning }}>
          <Row>
            <Ionicons name="alert-circle-outline" size={20} color={t.warning} />
            <Title>{data.pending_decisions} propuestas esperan tu decisión</Title>
          </Row>
        </Card>
      )}

      {canDecide && (
        <Row>
          <Button
            label="Sincronizar"
            variant="secondary"
            loading={busy === 'sync'}
            onPress={() => run('sync', api.sync, 'Tablero sincronizado con Trello.')}
          />
          <Button
            label="Analizar retrasos"
            loading={busy === 'analysis'}
            onPress={() =>
              run('analysis', api.runAnalysis,
                'Los agentes están analizando el proyecto. Las propuestas aparecerán en unos minutos.')
            }
          />
        </Row>
      )}

      <Section>Requieren atención ({data?.attention.length ?? 0})</Section>
      {data?.attention.length === 0 && <Body muted>No hay actividades retrasadas, bloqueadas ni en riesgo.</Body>}
      {data?.attention.map((a) => (
        <ActivityCard key={a.id} activity={a} />
      ))}

      {!!data?.jobs.length && (
        <>
          <Section>Tareas automáticas</Section>
          {data.jobs.map((j) => (
            <Row key={j.id}>
              <Badge label={{ analysis: 'Análisis', code: 'Código', report: 'Reporte' }[j.id] ?? j.id} color={t.info} />
              <Body muted>próxima: {fmtDate(j.next_run, true)}</Body>
            </Row>
          ))}
        </>
      )}
    </Screen>
  );
}
