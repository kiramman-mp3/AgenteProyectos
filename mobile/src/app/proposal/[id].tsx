import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, TextInput, View } from 'react-native';

import { Badge, Body, Button, Card, ErrorBox, Loading, Row, Screen, Section, Title, useLoader } from '@/components/ui';
import { api, Proposal } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { ACTION_LABEL, fmtDate, PROPOSAL_STATUS_LABEL, proposalColor, useTheme } from '@/lib/theme';

function describeParams(p: Proposal): string[] {
  const x = p.params as Record<string, any>;
  switch (p.action_type) {
    case 'reprogramar':
      return [`Nueva fecha límite: ${x.due}`, ...(x.start ? [`Nueva fecha de inicio: ${x.start}`] : [])];
    case 'cambiar_prioridad':
      return [`Nueva prioridad: ${x.priority}`];
    case 'reasignar':
      return [
        ...(x.add_members?.length ? [`Agregar: ${x.add_members.join(', ')}`] : []),
        ...(x.remove_members?.length ? [`Quitar: ${x.remove_members.join(', ')}`] : []),
      ];
    case 'cambiar_estado':
      return [`Mover a la lista: ${x.list_name}`];
    case 'comentar':
      return [`Comentario: "${x.text}"`];
    case 'crear_issue':
      return [`Título: ${x.title}`, String(x.body ?? '')];
    default:
      return [JSON.stringify(x)];
  }
}

function AgentStep({ title, verdict, color, notes }: { title: string; verdict?: string | null; color: string; notes?: string | null }) {
  return (
    <Card>
      <Row style={{ justifyContent: 'space-between' }}>
        <Title>{title}</Title>
        {verdict && <Badge label={verdict} color={color} />}
      </Row>
      <Body muted>{notes || 'Sin observaciones.'}</Body>
    </Card>
  );
}

export default function ProposalDetail() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { canDecide } = useAuth();
  const loader = useCallback(() => api.proposal(Number(id)), [id]);
  const { data: p, error, reload } = useLoader(loader);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  if (!p && !error) return <Loading />;
  if (!p) return <Screen><ErrorBox message={error!} /></Screen>;

  const decide = async (kind: 'approve' | 'reject' | 'changes') => {
    if (kind === 'changes' && comment.trim().length < 3) {
      Alert.alert('Falta el comentario', 'Describe qué modificación necesitas.');
      return;
    }
    setBusy(kind);
    try {
      if (kind === 'approve') {
        const r = await api.approve(p.id, comment || undefined);
        Alert.alert(r.status === 'ejecutada' ? 'Cambio ejecutado' : 'Resultado', `Estado: ${PROPOSAL_STATUS_LABEL[r.status] ?? r.status}`);
      } else if (kind === 'reject') {
        await api.reject(p.id, comment || undefined);
        Alert.alert('Propuesta rechazada', 'La decisión quedó registrada en la bitácora.');
      } else {
        await api.requestChanges(p.id, comment.trim());
        Alert.alert('Modificación solicitada', 'El Agente Ejecutor preparará una nueva versión que volverá a pasar por Revisor y Aprobador.');
      }
      router.back();
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : String(e));
      await reload();
    } finally {
      setBusy(null);
    }
  };

  const reviewerColor = p.reviewer_verdict === 'aprobada' ? t.success : p.reviewer_verdict ? t.danger : t.neutral;
  const approverColor = p.approver_decision === 'denegada' ? t.danger : p.approver_decision ? t.success : t.neutral;
  const pending = p.status === 'pendiente_gestor';

  return (
    <Screen>
      <Card>
        <Row style={{ justifyContent: 'space-between' }}>
          <Badge label={PROPOSAL_STATUS_LABEL[p.status] ?? p.status} color={proposalColor(t, p.status)} />
          <Body muted>#{p.id}{p.revision_of ? ` · revisión de #${p.revision_of}` : ''}</Body>
        </Row>
        <Title style={{ fontSize: 18 }}>{ACTION_LABEL[p.action_type] ?? p.action_type}</Title>
        <Body>{p.target_name ?? 'Repositorio'}</Body>
        {describeParams(p).map((line, i) => (
          <Body key={i} style={{ fontWeight: i === 0 ? '600' : '400' }}>{line}</Body>
        ))}
      </Card>

      <Section>Análisis del Agente Ejecutor</Section>
      <Card>
        {p.problem ? <><Title>Causa probable</Title><Body>{p.problem}</Body></> : null}
        {p.justification ? <><Title>Justificación</Title><Body>{p.justification}</Body></> : null}
        {p.impact ? <><Title>Impacto esperado</Title><Body>{p.impact}</Body></> : null}
      </Card>

      <Section>Flujo multiagente</Section>
      <AgentStep title="Agente Revisor" verdict={p.reviewer_verdict} color={reviewerColor} notes={p.reviewer_notes} />
      <AgentStep
        title="Agente Aprobador"
        verdict={p.approver_decision ? `${p.approver_decision.replace('_', ' ')} · riesgo ${p.approver_risk}` : null}
        color={approverColor}
        notes={p.approver_notes}
      />
      {(p.manager || p.execution_result) && (
        <Card>
          <Title>Decisión y ejecución</Title>
          {p.manager && <Body>Decidido por {p.manager} el {fmtDate(p.decided_at, true)}</Body>}
          {p.manager_comment && <Body muted>"{p.manager_comment}"</Body>}
          {p.execution_result && <Body>Resultado: {p.execution_result}</Body>}
        </Card>
      )}

      {!!p.alternatives?.length && (
        <>
          <Section>Otras alternativas para este problema</Section>
          {p.alternatives.map((a) => (
            <Card key={a.id} onPress={() => router.push({ pathname: '/proposal/[id]', params: { id: String(a.id) } })}>
              <Row style={{ justifyContent: 'space-between' }}>
                <Body>#{a.id} {ACTION_LABEL[a.action_type] ?? a.action_type}</Body>
                <Badge label={PROPOSAL_STATUS_LABEL[a.status] ?? a.status} color={proposalColor(t, a.status)} />
              </Row>
            </Card>
          ))}
        </>
      )}

      {pending && canDecide && (
        <>
          <Section>Tu decisión</Section>
          <TextInput
            value={comment}
            onChangeText={setComment}
            placeholder="Comentario (obligatorio para solicitar modificación)"
            placeholderTextColor={t.muted}
            multiline
            style={{
              minHeight: 80, borderWidth: 1, borderColor: t.border, borderRadius: 10, padding: 10,
              color: t.text, backgroundColor: t.card, textAlignVertical: 'top',
            }}
          />
          <Row>
            <Button label="Aprobar y ejecutar" onPress={() => decide('approve')} loading={busy === 'approve'} disabled={!!busy} />
          </Row>
          <Row>
            <Button label="Solicitar cambios" variant="secondary" onPress={() => decide('changes')} loading={busy === 'changes'} disabled={!!busy} />
            <Button label="Rechazar" variant="danger" onPress={() => decide('reject')} loading={busy === 'reject'} disabled={!!busy} />
          </Row>
        </>
      )}

      {!!p.history?.length && (
        <>
          <Section>Historial</Section>
          {p.history.map((h) => (
            <View key={h.id} style={{ flexDirection: 'row', gap: 8 }}>
              <Body muted style={{ width: 92 }}>{fmtDate(h.ts, true)}</Body>
              <Body style={{ flex: 1 }}>
                <Body style={{ fontWeight: '600' }}>{h.actor}</Body> · {h.action.replace(/_/g, ' ')}
              </Body>
            </View>
          ))}
        </>
      )}
    </Screen>
  );
}
