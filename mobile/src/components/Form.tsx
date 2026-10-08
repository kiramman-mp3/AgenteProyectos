import { useState } from 'react';
import { Alert, Pressable, Share, Text, TextInput, TextInputProps, View } from 'react-native';

import { api } from '@/lib/api';
import { useTheme } from '@/lib/theme';

import { Body, Button, Row } from './ui';

export function Field({ label, ...props }: TextInputProps & { label: string }) {
  const t = useTheme();
  return (
    <View style={{ gap: 4 }}>
      <Text style={{ color: t.muted, fontSize: 13, fontWeight: '600' }}>{label}</Text>
      <TextInput
        placeholderTextColor={t.muted}
        autoCapitalize="none"
        autoCorrect={false}
        {...props}
        style={[
          { borderWidth: 1, borderColor: t.border, borderRadius: 10, paddingHorizontal: 12, minHeight: 46,
            fontSize: 15, color: t.text, backgroundColor: t.card },
          props.style,
        ]}
      />
    </View>
  );
}

/** Selector de opciones en forma de botones segmentados. */
export function Segmented<T extends string>({
  value, options, onChange,
}: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', borderRadius: 10, borderWidth: 1, borderColor: t.border, overflow: 'hidden' }}>
      {options.map((o) => (
        <Pressable
          key={o.value}
          onPress={() => onChange(o.value)}
          style={{ flex: 1, padding: 10, alignItems: 'center', backgroundColor: value === o.value ? t.primary : t.card }}
        >
          <Text style={{ color: value === o.value ? t.primaryText : t.text, fontWeight: '600' }}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function ChangePasswordForm({ onDone, currentLabel = 'Contraseña actual' }: { onDone: () => void; currentLabel?: string }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false);
  const t = useTheme();

  const valid = next.length >= 8 && next === repeat && current.length > 0;
  const submit = async () => {
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setRepeat('');
      Alert.alert('Contraseña actualizada', 'Usa la nueva contraseña la próxima vez que ingreses.');
      onDone();
    } catch (e) {
      Alert.alert('No se pudo cambiar', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: 10 }}>
      <Field label={currentLabel} value={current} onChangeText={setCurrent} secureTextEntry />
      <Field label="Nueva contraseña (mínimo 8 caracteres)" value={next} onChangeText={setNext} secureTextEntry />
      <Field label="Repite la nueva contraseña" value={repeat} onChangeText={setRepeat} secureTextEntry />
      {repeat.length > 0 && next !== repeat && <Body style={{ color: t.danger }}>Las contraseñas no coinciden.</Body>}
      <Row>
        <Button label="Cambiar contraseña" onPress={submit} loading={busy} disabled={!valid} />
      </Row>
    </View>
  );
}

export function showTemporaryPassword(username: string, password: string) {
  Alert.alert(
    'Contraseña temporal',
    `Usuario: ${username}\nContraseña: ${password}\n\nCompártela con la persona: deberá cambiarla en su primer ingreso. No se volverá a mostrar.`,
    [
      { text: 'Compartir', onPress: () => Share.share({ message: `Agente de Proyectos\nUsuario: ${username}\nContraseña temporal: ${password}` }) },
      { text: 'Listo' },
    ],
  );
}
