import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Alert } from 'react-native';

import { Field, Segmented, showTemporaryPassword } from '@/components/Form';
import { Badge, Body, Button, Card, ErrorBox, Loading, Row, Screen, Section, Title, useLoader } from '@/components/ui';
import { api, Role } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { fmtDate, ROLE_LABEL, useTheme } from '@/lib/theme';

export default function UserDetail() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { session } = useAuth();
  const loader = useCallback(async () => (await api.users()).find((u) => u.id === Number(id)) ?? null, [id]);
  const { data: u, error, reload } = useLoader(loader);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Role>('desarrollador');
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (u) {
      setFullName(u.full_name ?? '');
      setEmail(u.email ?? '');
      setRole(u.role === 'admin' ? 'gestor' : u.role === 'observador' ? 'desarrollador' : u.role);
    }
  }, [u]);

  if (!u && !error) return <Loading />;
  if (!u) return <Screen><ErrorBox message={error ?? 'Usuario no encontrado'} /></Screen>;
  const isMe = u.username === session?.username;

  const run = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    try {
      await fn();
      await reload();
      if (ok) Alert.alert('Listo', ok);
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Screen>
      <Card>
        <Row style={{ justifyContent: 'space-between' }}>
          <Title style={{ fontSize: 18 }}>@{u.username}</Title>
          <Badge label={u.active ? 'Activo' : 'Desactivado'} color={u.active ? t.success : t.danger} />
        </Row>
        <Body muted>Creado el {fmtDate(u.created_at)} · {ROLE_LABEL[u.role] ?? u.role}</Body>
      </Card>

      <Section>Datos</Section>
      <Card>
        <Field label="Nombre completo" value={fullName} onChangeText={setFullName} autoCapitalize="words" />
        <Field label="Correo" value={email} onChangeText={setEmail} keyboardType="email-address" />
        {!isMe && (
          <Segmented
            value={role}
            onChange={setRole}
            options={[{ value: 'desarrollador', label: 'Desarrollador' }, { value: 'gestor', label: 'Gestor' }]}
          />
        )}
        {(u.role === 'gestor' || u.role === 'admin') && (
          <Body muted>Los gestores reciben por correo los avisos de retrasos críticos.</Body>
        )}
        <Row>
          <Button
            label="Guardar cambios"
            loading={busy === 'save'}
            onPress={() =>
              run('save', () => api.updateUser(u.id, { full_name: fullName.trim(), email: email.trim(),
                                                        ...(isMe ? {} : { role }) }), 'Datos actualizados.')
            }
          />
        </Row>
      </Card>

      {!isMe && (
        <>
          <Section>Acceso</Section>
          <Row>
            <Button
              label="Restablecer contraseña"
              variant="secondary"
              loading={busy === 'reset'}
              onPress={() =>
                run('reset', async () => {
                  const r = await api.resetPassword(u.id);
                  showTemporaryPassword(r.username, r.temporary_password);
                })
              }
            />
          </Row>
          <Row>
            <Button
              label={u.active ? 'Desactivar usuario' : 'Reactivar usuario'}
              variant={u.active ? 'danger' : 'primary'}
              loading={busy === 'active'}
              onPress={() =>
                run('active', () => api.updateUser(u.id, { active: !u.active }),
                    u.active ? 'El usuario ya no podrá ingresar.' : 'El usuario puede volver a ingresar.')
              }
            />
          </Row>
        </>
      )}
    </Screen>
  );
}
