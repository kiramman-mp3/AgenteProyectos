import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';

import { Body, Button, ErrorBox } from '@/components/ui';
import { getServerUrl } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useTheme } from '@/lib/theme';

export default function Login() {
  const t = useTheme();
  const { login } = useAuth();
  const [server, setServer] = useState('https://agente-proyectos-hy7x.onrender.com');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getServerUrl().then((s) => s && setServer(s));
  }, []);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await login(server, username.trim(), password);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const input = [styles.input, { color: t.text, borderColor: t.border, backgroundColor: t.card }];

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={[styles.container, { backgroundColor: t.bg }]}
    >
      <View style={{ gap: 4, marginBottom: 16 }}>
        <Text style={{ color: t.text, fontSize: 26, fontWeight: '700' }}>Agente de Proyectos</Text>
        <Body muted>Seguimiento y control con agentes Ejecutor, Revisor y Aprobador</Body>
      </View>

      <Text style={[styles.label, { color: t.muted }]}>Servidor</Text>
      <TextInput
        style={input}
        value={server}
        onChangeText={setServer}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        placeholder="https://mi-servidor.com"
        placeholderTextColor={t.muted}
      />
      <Text style={[styles.label, { color: t.muted }]}>Usuario</Text>
      <TextInput
        style={input}
        value={username}
        onChangeText={setUsername}
        autoCapitalize="none"
        autoCorrect={false}
        placeholderTextColor={t.muted}
      />
      <Text style={[styles.label, { color: t.muted }]}>Contraseña</Text>
      <TextInput
        style={input}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        onSubmitEditing={submit}
        placeholderTextColor={t.muted}
      />
      {error && <ErrorBox message={error} />}
      <View style={{ flexDirection: 'row', marginTop: 8 }}>
        <Button label="Ingresar" onPress={submit} loading={busy} disabled={!username || !password} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 24, gap: 8 },
  label: { fontSize: 13, fontWeight: '600', marginTop: 4 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, minHeight: 46, fontSize: 15 },
});
