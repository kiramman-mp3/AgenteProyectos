import { ReactNode } from 'react';
import { Text, View } from 'react-native';

import { useTheme } from '@/lib/theme';

/** Renderizador mínimo para el Markdown que genera el backend: títulos, listas, tablas, **negrita**, *cursiva*. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <Text key={`${keyPrefix}-${i}`} style={{ fontWeight: '700' }}>{part.slice(2, -2)}</Text>;
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2)
      return <Text key={`${keyPrefix}-${i}`} style={{ fontStyle: 'italic' }}>{part.slice(1, -1)}</Text>;
    return part;
  });
}

export function Markdown({ children }: { children: string }) {
  const t = useTheme();
  const lines = children.split('\n');
  const out: ReactNode[] = [];
  const text = { color: t.text, fontSize: 14, lineHeight: 20 };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const key = `l${i}`;
    if (line.startsWith('|')) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith('|')) {
        const cells = lines[i].split('|').slice(1, -1).map((c) => c.trim());
        if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells);
        i++;
      }
      i--;
      out.push(
        <View key={key} style={{ borderWidth: 1, borderColor: t.border, borderRadius: 8, marginVertical: 6 }}>
          {rows.map((r, ri) => (
            <View key={ri} style={{ flexDirection: 'row', borderTopWidth: ri ? 1 : 0, borderColor: t.border }}>
              {r.map((c, ci) => (
                <Text key={ci} style={[text, { flex: 1, padding: 6, fontWeight: ri === 0 ? '700' : '400' }]}>{c}</Text>
              ))}
            </View>
          ))}
        </View>,
      );
    } else if (/^#{1,3} /.test(line)) {
      const level = line.indexOf(' ');
      const size = { 1: 20, 2: 17, 3: 15 }[level] ?? 15;
      out.push(
        <Text key={key} style={[text, { fontSize: size, fontWeight: '700', marginTop: level === 1 ? 0 : 12 }]}>
          {inline(line.slice(level + 1), key)}
        </Text>,
      );
    } else if (/^\s*([-*]|\d+\.) /.test(line)) {
      const m = line.match(/^(\s*)([-*]|\d+\.) (.*)$/)!;
      out.push(
        <View key={key} style={{ flexDirection: 'row', paddingLeft: m[1].length * 6, gap: 6 }}>
          <Text style={text}>{m[2] === '-' || m[2] === '*' ? '•' : m[2]}</Text>
          <Text style={[text, { flex: 1 }]}>{inline(m[3], key)}</Text>
        </View>,
      );
    } else if (line.trim() === '---') {
      out.push(<View key={key} style={{ height: 1, backgroundColor: t.border, marginVertical: 10 }} />);
    } else if (line.trim()) {
      out.push(<Text key={key} style={text}>{inline(line, key)}</Text>);
    } else {
      out.push(<View key={key} style={{ height: 6 }} />);
    }
  }
  return <View>{out}</View>;
}
