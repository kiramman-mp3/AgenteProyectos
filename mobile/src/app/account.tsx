import { router } from 'expo-router';
import { Alert } from 'react-native';

import { ChangePasswordForm } from '@/components/Form';
import { Badge, Body, Button, Card, Loading, Row, Screen, Section, Title, useLoader } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { ROLE_LABEL, useTheme } from '@/lib/theme';

export default function AccountScreen() {
  const t = useTheme();
  const { logout, canDecide } = useAuth();
  const { data: me } = useLoader(api.me);

  if (!me) return <Loading />;
  return (
    <Screen>
      <Card>
        <Title style={{ fontSize: 20 }}>{me.full_name || me.username}</Title>
        <Body muted>@{me.username}{me.email ? ` · ${me.email}` : ''}</Body>
        <Badge label={ROLE_LABEL[me.role] ?? me.role} color={canDecide ? t.primary : t.success} />
      </Card>

      {canDecide && (
        <>
          <Section>Equipo</Section>
          <Card onPress={() => router.push('/users')}>
            <Title>Gestionar usuarios</Title>
            <Body muted>Crear cuentas para los desarrolladores, cambiar roles y restablecer contraseñas.</Body>
          </Card>
          {!me.email && (
            <Body style={{ color: t.warning }}>
              Agrega tu correo en Gestionar usuarios para recibir los avisos de retrasos críticos.
            </Body>
          )}
        </>
      )}

      <Section>Cambiar contraseña</Section>
      <Card>
        <ChangePasswordForm onDone={() => {}} />
      </Card>

      <Row>
        <Button
          label="Cerrar sesión"
          variant="danger"
          onPress={() =>
            Alert.alert('Cerrar sesión', '¿Deseas salir?', [
              { text: 'Cancelar', style: 'cancel' },
              { text: 'Salir', style: 'destructive', onPress: () => void logout() },
            ])
          }
        />
      </Row>
    </Screen>
  );
}
