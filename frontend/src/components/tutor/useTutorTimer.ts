import { useEffect, useRef } from 'react';

import { usePomodoroController } from '../../features/pomodoro/PomodoroProvider';
import { toTutorTimerState } from '../../utils/pomodoro';
import type { Language } from '../../utils/settings';

interface UseTutorTimerOptions {
  language: Language;
  onPomodoroLogged?: () => void;
  onTimerMessage: (content: string) => void;
}

export function useTutorTimer({
  language,
  onPomodoroLogged,
  onTimerMessage,
}: UseTutorTimerOptions) {
  const { state, lastEvent, logVersion, resetTimer, startNextRound, toggleTimer } =
    usePomodoroController();
  const lastSeenEventIdRef = useRef<number | null>(lastEvent?.id ?? null);
  const lastSeenLogVersionRef = useRef(logVersion);

  useEffect(() => {
    if (!lastEvent || lastEvent.id === lastSeenEventIdRef.current) return;
    lastSeenEventIdRef.current = lastEvent.id;

    if (lastEvent.kind !== 'focus-complete') return;

    onTimerMessage(
      language === 'zh'
        ? `本轮专注结束。休息 ${lastEvent.breakMinutes} 分钟，然后继续下一轮。`
        : `Focus round complete. Take a ${lastEvent.breakMinutes}-minute break, then continue.`,
    );
  }, [language, lastEvent, onTimerMessage]);

  useEffect(() => {
    if (logVersion === lastSeenLogVersionRef.current) return;
    lastSeenLogVersionRef.current = logVersion;
    onPomodoroLogged?.();
  }, [logVersion, onPomodoroLogged]);

  return {
    remainingSeconds: state.remainingSeconds,
    timerState: toTutorTimerState(state.mode),
    isRunning: state.isRunning,
    timerHasStarted: state.timerHasStarted,
    completedFocusRounds: state.completedFocusRounds,
    resetTimer,
    startNextRound,
    toggleTimer,
  };
}
