export type PomodoroMode = 'work' | 'shortBreak' | 'longBreak';
export type TutorTimerState = 'focus' | Exclude<PomodoroMode, 'work'>;

export interface PomodoroState {
  workDuration: number;
  shortBreakDuration: number;
  longBreakDuration: number;
  mode: PomodoroMode;
  remainingSeconds: number;
  targetEndAt: number | null;
  isRunning: boolean;
  timerHasStarted: boolean;
  completedFocusRounds: number;
  completedPomodoros: number;
  focusMinutes: number;
}

export interface PomodoroCompletionEvent {
  kind: 'focus-complete' | 'break-complete';
  nextMode: PomodoroMode;
  breakMinutes: number;
  focusLogMinutes: number;
}

export interface PomodoroCompletionResult {
  state: PomodoroState;
  event: PomodoroCompletionEvent;
}

export interface PomodoroReconcileResult {
  state: PomodoroState;
  event: PomodoroCompletionEvent | null;
}

export const POMODORO_DURATIONS: Record<PomodoroMode, number> = {
  work: 45,
  shortBreak: 10,
  longBreak: 20,
};

export function getBreakModeForCompletedFocusRound(
  completedFocusRounds: number,
): 'shortBreak' | 'longBreak' {
  return completedFocusRounds % 2 === 0 ? 'longBreak' : 'shortBreak';
}

export function getPomodoroDurationSeconds(
  mode: PomodoroMode,
  durations: Pick<PomodoroState, 'workDuration' | 'shortBreakDuration' | 'longBreakDuration'> = {
    workDuration: POMODORO_DURATIONS.work,
    shortBreakDuration: POMODORO_DURATIONS.shortBreak,
    longBreakDuration: POMODORO_DURATIONS.longBreak,
  },
): number {
  if (mode === 'work') return durations.workDuration * 60;
  if (mode === 'shortBreak') return durations.shortBreakDuration * 60;
  return durations.longBreakDuration * 60;
}

export function createInitialPomodoroState(): PomodoroState {
  return {
    workDuration: POMODORO_DURATIONS.work,
    shortBreakDuration: POMODORO_DURATIONS.shortBreak,
    longBreakDuration: POMODORO_DURATIONS.longBreak,
    mode: 'work',
    remainingSeconds: getPomodoroDurationSeconds('work'),
    targetEndAt: null,
    isRunning: false,
    timerHasStarted: false,
    completedFocusRounds: 0,
    completedPomodoros: 0,
    focusMinutes: 0,
  };
}

export function getPomodoroTargetEndAt(remainingSeconds: number, now = Date.now()): number {
  return now + remainingSeconds * 1000;
}

export function clampPomodoroDuration(mode: PomodoroMode, durationMinutes: number): number {
  if (mode === 'work') return Math.max(1, Math.min(60, durationMinutes));
  if (mode === 'shortBreak') return Math.max(1, Math.min(30, durationMinutes));
  return Math.max(1, Math.min(60, durationMinutes));
}

export function resetPomodoroState(state: PomodoroState): PomodoroState {
  return {
    ...state,
    mode: 'work',
    remainingSeconds: getPomodoroDurationSeconds('work', state),
    targetEndAt: null,
    isRunning: false,
    timerHasStarted: false,
    completedFocusRounds: 0,
  };
}

export function togglePomodoroTimer(state: PomodoroState, now = Date.now()): PomodoroState {
  if (state.isRunning) {
    return {
      ...state,
      isRunning: false,
      targetEndAt: null,
    };
  }

  return {
    ...state,
    isRunning: true,
    timerHasStarted: true,
    targetEndAt: getPomodoroTargetEndAt(state.remainingSeconds, now),
  };
}

export function startNextPomodoroRound(state: PomodoroState, now = Date.now()): PomodoroState {
  return {
    ...state,
    mode: 'work',
    remainingSeconds: getPomodoroDurationSeconds('work', state),
    targetEndAt: getPomodoroTargetEndAt(getPomodoroDurationSeconds('work', state), now),
    timerHasStarted: true,
    isRunning: true,
  };
}

export function switchPomodoroMode(state: PomodoroState, nextMode: PomodoroMode): PomodoroState {
  return {
    ...state,
    mode: nextMode,
    remainingSeconds: getPomodoroDurationSeconds(nextMode, state),
    targetEndAt: null,
    isRunning: false,
  };
}

export function adjustPomodoroDuration(
  state: PomodoroState,
  mode: PomodoroMode,
  increment: boolean,
): PomodoroState {
  const adjustment = increment ? 1 : -1;
  const nextDuration = clampPomodoroDuration(
    mode,
    (mode === 'work'
      ? state.workDuration
      : mode === 'shortBreak'
        ? state.shortBreakDuration
        : state.longBreakDuration) + adjustment,
  );

  const nextState: PomodoroState = {
    ...state,
    workDuration: mode === 'work' ? nextDuration : state.workDuration,
    shortBreakDuration: mode === 'shortBreak' ? nextDuration : state.shortBreakDuration,
    longBreakDuration: mode === 'longBreak' ? nextDuration : state.longBreakDuration,
  };

  if (!state.isRunning && state.mode === mode) {
    nextState.remainingSeconds = getPomodoroDurationSeconds(mode, nextState);
  }

  return nextState;
}

export function resolvePomodoroCompletion(state: PomodoroState): PomodoroCompletionResult {
  if (state.mode === 'work') {
    const completedFocusRounds = state.completedFocusRounds + 1;
    const nextMode = getBreakModeForCompletedFocusRound(completedFocusRounds);

    return {
      state: {
        ...state,
        mode: nextMode,
        remainingSeconds: getPomodoroDurationSeconds(nextMode, state),
        targetEndAt: null,
        isRunning: false,
        completedFocusRounds,
        completedPomodoros: state.completedPomodoros + 1,
        focusMinutes: state.focusMinutes + state.workDuration,
      },
      event: {
        kind: 'focus-complete',
        nextMode,
        breakMinutes:
          nextMode === 'shortBreak' ? state.shortBreakDuration : state.longBreakDuration,
        focusLogMinutes: state.workDuration,
      },
    };
  }

  return {
    state: {
      ...state,
      mode: 'work',
      remainingSeconds: getPomodoroDurationSeconds('work', state),
      targetEndAt: null,
      isRunning: false,
    },
    event: {
      kind: 'break-complete',
      nextMode: 'work',
      breakMinutes: state.workDuration,
      focusLogMinutes: 0,
    },
  };
}

export function normalizePomodoroState(value: unknown): PomodoroState {
  if (!value || typeof value !== 'object') {
    return createInitialPomodoroState();
  }

  const candidate = value as Partial<Record<keyof PomodoroState, unknown>>;
  const workDuration = clampPomodoroDuration(
    'work',
    Number(candidate.workDuration) || POMODORO_DURATIONS.work,
  );
  const shortBreakDuration = clampPomodoroDuration(
    'shortBreak',
    Number(candidate.shortBreakDuration) || POMODORO_DURATIONS.shortBreak,
  );
  const longBreakDuration = clampPomodoroDuration(
    'longBreak',
    Number(candidate.longBreakDuration) || POMODORO_DURATIONS.longBreak,
  );
  const mode: PomodoroMode =
    candidate.mode === 'shortBreak' || candidate.mode === 'longBreak' || candidate.mode === 'work'
      ? candidate.mode
      : 'work';

  const baseState: PomodoroState = {
    workDuration,
    shortBreakDuration,
    longBreakDuration,
    mode,
    remainingSeconds: getPomodoroDurationSeconds(mode, {
      workDuration,
      shortBreakDuration,
      longBreakDuration,
    }),
    targetEndAt: null,
    isRunning: Boolean(candidate.isRunning),
    timerHasStarted: Boolean(candidate.timerHasStarted),
    completedFocusRounds: Math.max(0, Number(candidate.completedFocusRounds) || 0),
    completedPomodoros: Math.max(0, Number(candidate.completedPomodoros) || 0),
    focusMinutes: Math.max(0, Number(candidate.focusMinutes) || 0),
  };

  const remainingSeconds = Math.max(
    1,
    Math.min(
      getPomodoroDurationSeconds(mode, baseState),
      Number(candidate.remainingSeconds) || baseState.remainingSeconds,
    ),
  );

  const normalizedState: PomodoroState = {
    ...baseState,
    remainingSeconds,
    targetEndAt:
      baseState.isRunning && Number.isFinite(candidate.targetEndAt)
        ? Number(candidate.targetEndAt)
        : baseState.isRunning
          ? getPomodoroTargetEndAt(remainingSeconds)
          : null,
  };

  return baseState.isRunning ? reconcilePomodoroState(normalizedState).state : normalizedState;
}

export function reconcilePomodoroState(
  state: PomodoroState,
  now = Date.now(),
): PomodoroReconcileResult {
  if (!state.isRunning) {
    return {
      state: state.targetEndAt === null ? state : { ...state, targetEndAt: null },
      event: null,
    };
  }

  const targetEndAt = state.targetEndAt ?? getPomodoroTargetEndAt(state.remainingSeconds, now);
  const remainingSeconds = Math.max(0, Math.ceil((targetEndAt - now) / 1000));

  if (remainingSeconds > 0) {
    return {
      state:
        remainingSeconds === state.remainingSeconds && targetEndAt === state.targetEndAt
          ? state
          : { ...state, remainingSeconds, targetEndAt },
      event: null,
    };
  }

  const completion = resolvePomodoroCompletion({ ...state, remainingSeconds: 0, targetEndAt });
  return {
    state: completion.state,
    event: completion.event,
  };
}

export function toTutorTimerState(mode: PomodoroMode): TutorTimerState {
  return mode === 'work' ? 'focus' : mode;
}

export interface TutorTimerCompletion {
  timerState: TutorTimerState;
  remainingSeconds: number;
  completedFocusRounds: number;
  focusLogMinutes: number;
}

export function resolveTutorTimerCompletion(
  timerState: TutorTimerState,
  completedFocusRounds: number,
): TutorTimerCompletion {
  const currentState = createInitialPomodoroState();
  currentState.mode = timerState === 'focus' ? 'work' : timerState;
  currentState.completedFocusRounds = completedFocusRounds;
  const completion = resolvePomodoroCompletion(currentState);

  return {
    timerState: toTutorTimerState(completion.state.mode),
    remainingSeconds: completion.state.remainingSeconds,
    completedFocusRounds: completion.state.completedFocusRounds,
    focusLogMinutes: completion.event.focusLogMinutes,
  };
}
