import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { Field, Segmented, showTemporaryPassword } from '@/components/Form';
import { Badge, Body, Button, Card, ErrorBox, Loading, Row, Screen, Section, Title, useLoader } from '@/components/ui';
import { api, Role } from '@/lib/api';
import { ROLE_LABEL, useTheme } from '@/lib/theme';

export default function UsersScreen() {
  const t = useTheme();
  const { data, error, refreshing, refresh, reload } = useLoader(api.users);
  const [creating, setCreating] = useState(false);
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Role>('desarrollador');
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try {
      const u = await api.createUser({ username: username.trim(), full_name: fullName.trim(), email: email.trim(), role });
      setUsername('');
      setFullName('');
      setEmail('');
      setCreating(false);
      await reload();
      showTemporaryPassword(u.username, u.temporary_password);
    } catch (e) {
      Alert.alert('No se pudo crear', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!data && !error) return <Loading />;
  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      {error && <ErrorBox message={error} />}
      {!creating ? (
        <Row>
          <Button label="Nuevo usuario" onPress={() => setCreating(true)} />
        </Row>
      ) : (
        <Card>
          <Title>Nuevo usuario</Title>
          <Field label="Usuario (sin espacios)" value={username} onChangeText={setUsername} placeholder="carol" />
          <Field label="Nombre completo" value={fullName} onChangeText={setFullName} autoCapitalize="words" />
          <Field label="Correo (opcional)" value={email} onChangeText={setEmail} keyboardType="email-address" />
          <Segmented
            value={role}
            onChange={setRole}
            options={[{ value: 'desarrollador', label: 'Desarrollador' }, { value: 'gestor', label: 'Gestor' }]}
          />
          <Body muted>Se generará una contraseña temporal que la persona cambiará en su primer ingreso.</Body>
          <Row>
            <Button label="Cancelar" variant="secondary" onPress={() => setCreating(false)} />
            <Button label="Crear" onPress={create} loading={busy} disabled={username.trim().length < 3} />
          </Row>
        </Card>
      )}

      <Section>Usuarios ({data?.length ?? 0})</Section>
      {data?.map((u) => (
        <Card key={u.id} onPress={() => router.push({ pathname: '/user/[id]', params: { id: String(u.id) } })}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Title>{u.full_name || u.username}</Title>
            <Badge label={ROLE_LABEL[u.role] ?? u.role} color={u.role === 'gestor' || u.role === 'admin' ? t.primary : t.success} />
          </Row>
          <Body muted>@{u.username}{u.email ? ` · ${u.email}` : ''}</Body>
          <Row>
            {!u.active && <Badge label="Desactivado" color={t.danger} />}
            {!!u.must_change_password && u.active === 1 && <Badge label="Contraseña temporal" color={t.warning} />}
          </Row>
        </Card>
      ))}
    </Screen>
  );
}
