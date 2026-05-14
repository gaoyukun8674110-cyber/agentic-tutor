import type { PomodoroMode } from '../../utils/pomodoro';

export type ChatRole = 'user' | 'assistant';
export type TimerState = 'focus' | Exclude<PomodoroMode, 'work'>;

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  label?: string;
  credentialSource?: 'user' | 'global' | 'local';
  credentialFingerprint?: string | null;
}
