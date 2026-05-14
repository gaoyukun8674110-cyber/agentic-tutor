import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { logDashboardPomodoro } from '../../utils/dashboardApi';
import {
  adjustPomodoroDuration,
  createInitialPomodoroState,
  normalizePomodoroState,
  reconcilePomodoroState,
  resetPomodoroState,
  startNextPomodoroRound,
  switchPomodoroMode,
  togglePomodoroTimer,
  type PomodoroCompletionEvent,
  type PomodoroMode,
  type PomodoroState,
} from '../../utils/pomodoro';

const POMODORO_STORAGE_KEY = 'ai-tutor-pomodoro-state-v1';
const POMODORO_NOTIFICATION_PERMISSION_KEY = 'ai-tutor-pomodoro-notification-requested';

interface PomodoroRuntimeEvent extends PomodoroCompletionEvent {
  id: number;
}

interface PomodoroContextValue {
  state: PomodoroState;
  lastEvent: PomodoroRuntimeEvent | null;
  logVersion: number;
  toggleTimer: () => void;
  resetTimer: () => void;
  startNextRound: () => void;
  switchMode: (mode: PomodoroMode) => void;
  adjustDuration: (mode: PomodoroMode, increment: boolean) => void;
}

const PomodoroContext = createContext<PomodoroContextValue | null>(null);

function readStoredPomodoroState(): PomodoroState {
  if (typeof window === 'undefined') {
    return createInitialPomodoroState();
  }

  const raw = window.localStorage.getItem(POMODORO_STORAGE_KEY);
  if (!raw) {
    return createInitialPomodoroState();
  }

  try {
    return normalizePomodoroState(JSON.parse(raw));
  } catch {
    return createInitialPomodoroState();
  }
}

export function PomodoroProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PomodoroState>(() => readStoredPomodoroState());
  const [lastEvent, setLastEvent] = useState<PomodoroRuntimeEvent | null>(null);
  const [logVersion, setLogVersion] = useState(0);
  const latestStateRef = useRef(state);
  const nextEventIdRef = useRef(1);
  const notificationPermissionRequestedRef = useRef(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    notificationPermissionRequestedRef.current =
      window.localStorage.getItem(POMODORO_NOTIFICATION_PERMISSION_KEY) === 'true';
  }, []);

  useEffect(() => {
    latestStateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(POMODORO_STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const syncState = (event: StorageEvent) => {
      if (event.key !== POMODORO_STORAGE_KEY) return;
      try {
        setState(normalizePomodoroState(event.newValue ? JSON.parse(event.newValue) : null));
      } catch {
        setState(createInitialPomodoroState());
      }
    };

    window.addEventListener('storage', syncState);
    return () => window.removeEventListener('storage', syncState);
  }, []);

  useEffect(() => {
    if (!state.isRunning) return;

    const timer = window.setInterval(() => {
      const result = reconcilePomodoroState(latestStateRef.current, Date.now());

      if (!result.event) {
        if (result.state !== latestStateRef.current) {
          setState(result.state);
        }
        return;
      }
      const eventId = nextEventIdRef.current++;

      setState(result.state);
      setLastEvent({ ...result.event, id: eventId });

      if (result.event.focusLogMinutes > 0) {
        void logDashboardPomodoro(result.event.focusLogMinutes, 'work')
          .then(() => setLogVersion((version) => version + 1))
          .catch(() => {
            // Keep the shared timer usable even when persistence is temporarily unavailable.
          });
      }

      if ('Notification' in window && Notification.permission === 'granted' && result.event.kind === 'focus-complete') {
        new Notification('Pomodoro', {
          body: `Focus block finished. Take a ${result.event.breakMinutes}-minute break.`,
        });
      }
    }, 1000);

    return () => window.clearInterval(timer);
  }, [state.isRunning]);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    const reconcileVisibleTimer = () => {
      if (document.visibilityState !== 'visible') return;
      const result = reconcilePomodoroState(latestStateRef.current, Date.now());
      if (result.event) {
        const eventId = nextEventIdRef.current++;
        setState(result.state);
        setLastEvent({ ...result.event, id: eventId });
        return;
      }

      if (result.state !== latestStateRef.current) {
        setState(result.state);
      }
    };

    document.addEventListener('visibilitychange', reconcileVisibleTimer);
    return () => document.removeEventListener('visibilitychange', reconcileVisibleTimer);
  }, []);

  const value = useMemo<PomodoroContextValue>(
    () => ({
      state,
      lastEvent,
      logVersion,
      toggleTimer: () => {
        if (
          typeof window !== 'undefined' &&
          'Notification' in window &&
          Notification.permission === 'default' &&
          !notificationPermissionRequestedRef.current
        ) {
          notificationPermissionRequestedRef.current = true;
          window.localStorage.setItem(POMODORO_NOTIFICATION_PERMISSION_KEY, 'true');
          void Notification.requestPermission();
        }

        setState((previous) => togglePomodoroTimer(previous, Date.now()));
      },
      resetTimer: () => setState((previous) => resetPomodoroState(previous)),
      startNextRound: () => setState((previous) => startNextPomodoroRound(previous, Date.now())),
      switchMode: (mode) => setState((previous) => switchPomodoroMode(previous, mode)),
      adjustDuration: (mode, increment) => setState((previous) => adjustPomodoroDuration(previous, mode, increment)),
    }),
    [lastEvent, logVersion, state],
  );

  return <PomodoroContext.Provider value={value}>{children}</PomodoroContext.Provider>;
}

export function usePomodoroController() {
  const context = useContext(PomodoroContext);

  if (!context) {
    throw new Error('usePomodoroController must be used within PomodoroProvider');
  }

  return context;
}
