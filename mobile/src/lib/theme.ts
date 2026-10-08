import { useColorScheme } from 'react-native';

const light = {
  bg: '#F4F5F7',
  card: '#FFFFFF',
  text: '#172B4D',
  muted: '#5E6C84',
  border: '#DFE1E6',
  primary: '#0C66E4',
  primaryText: '#FFFFFF',
  success: '#1F845A',
  warning: '#B65C02',
  danger: '#C9372C',
  info: '#0C66E4',
  neutral: '#626F86',
  track: '#DFE1E6',
};

const dark: typeof light = {
  bg: '#1D2125',
  card: '#22272B',
  text: '#DEE4EA',
  muted: '#9FADBC',
  border: '#38414A',
  primary: '#579DFF',
  primaryText: '#1D2125',
  success: '#4BCE97',
  warning: '#F5CD47',
  danger: '#F87168',
  info: '#579DFF',
  neutral: '#8C9BAB',
  track: '#38414A',
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

export const STATUS_LABEL: Record<string, string> = {
  pendiente: 'Pendiente',
  en_ejecucion: 'En ejecución',
  completada: 'Completada',
  retrasada: 'Retrasada',
  bloqueada: 'Bloqueada',
};

export function statusColor(t: Theme, status: string): string {
  return (
    { pendiente: t.neutral, en_ejecucion: t.info, completada: t.success, retrasada: t.danger, bloqueada: t.warning }[
      status
    ] ?? t.neutral
  );
}

export const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  en_revision: 'En revisión',
  rechazada_revisor: 'Rechazada por Revisor',
  denegada_aprobador: 'Denegada por Aprobador',
  pendiente_gestor: 'Pendiente de tu decisión',
  aprobada: 'Aprobada',
  auto_aprobada: 'Autorizada por política',
  rechazada_gestor: 'Rechazada por gestor',
  modificacion_solicitada: 'Modificación solicitada',
  ejecutada: 'Ejecutada',
  fallida: 'Falló la ejecución',
  descartada: 'Descartada',
};

export function proposalColor(t: Theme, status: string): string {
  if (status === 'pendiente_gestor') return t.warning;
  if (status === 'ejecutada' || status === 'aprobada' || status === 'auto_aprobada') return t.success;
  if (status.startsWith('rechazada') || status === 'denegada_aprobador' || status === 'fallida') return t.danger;
  return t.neutral;
}

export const ACTION_LABEL: Record<string, string> = {
  reprogramar: 'Reprogramar',
  cambiar_prioridad: 'Cambiar prioridad',
  reasignar: 'Reasignar responsables',
  cambiar_estado: 'Cambiar estado',
  comentar: 'Comentar en tarjeta',
  crear_issue: 'Crear issue en GitHub',
};

export function severityColor(t: Theme, s: string): string {
  return { critica: t.danger, alta: t.danger, media: t.warning, baja: t.neutral }[s] ?? t.neutral;
}

export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return withTime
    ? d.toLocaleString('es-EC', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('es-EC', { day: '2-digit', month: 'short', year: 'numeric' });
}
