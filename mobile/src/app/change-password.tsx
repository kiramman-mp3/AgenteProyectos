import { KeyboardAvoidingView, Platform, ScrollView } from 'react-native';

import { ChangePasswordForm } from '@/components/Form';
import { Body, Button, Card, Row, Title } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { useTheme } from '@/lib/theme';

/** Se muestra obligatoriamente en el primer ingreso o tras un restablecimiento de contraseña. */
export default function ForcedChangePassword() {
  const t = useTheme();
  const { session, passwordChanged, logout } = useAuth();
  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: t.bg }}>
      <ScrollView contentContainerStyle={{ padding: 24, gap: 14, flexGrow: 1, justifyContent: 'center' }}>
        <Title style={{ fontSize: 24 }}>Crea tu contraseña</Title>
        <Body muted>
          Hola {session?.full_name || session?.username}. Estás usando una contraseña temporal: cámbiala por una
          personal para continuar.
        </Body>
        <Card>
          <ChangePasswordForm currentLabel="Contraseña temporal" onDone={() => void passwordChanged()} />
        </Card>
        <Row>
          <Button label="Salir" variant="secondary" onPress={() => void logout()} />
        </Row>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
