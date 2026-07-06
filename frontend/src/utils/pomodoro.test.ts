import { describe, expect, it, vi } from 'vitest';

import {
  adjustPomodoroDuration,
  createInitialPomodoroState,
  getBreakModeForCompletedFocusRound,
  getPomodoroDurationSeconds,
  normalizePomodoroState,
  reconcilePomodoroState,
  resolvePomodoroCompletion,
  resolveTutorTimerCompletion,
  startNextPomodoroRound,
} from './pomodoro';

describe('pomodoro utilities', () => {
  it('alternates break mode after focus rounds', () => {
    expect(getBreakModeForCompletedFocusRound(1)).toBe('shortBreak');
    expect(getBreakModeForCompletedFocusRound(2)).toBe('longBreak');
    expect(getBreakModeForCompletedFocusRound(3)).toBe('shortBreak');
  });

  it('returns the configured duration in seconds', () => {
    expect(getPomodoroDurationSeconds('work')).toBe(45 * 60);
    expect(getPomodoroDurationSeconds('shortBreak')).toBe(10 * 60);
    expect(getPomodoroDurationSeconds('longBreak')).toBe(20 * 60);
  });

  it('creates an initial unified timer state', () => {
    expect(createInitialPomodoroState()).toEqual({
      workDuration: 45,
      shortBreakDuration: 10,
      longBreakDuration: 20,
      mode: 'work',
      remainingSeconds: 45 * 60,
      isRunning: false,
      timerHasStarted: false,
      completedFocusRounds: 0,
      completedPomodoros: 0,
      focusMinutes: 0,
      targetEndAt: null,
    });
  });

  it('clamps restored persisted timer state to safe values', () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);

    expect(
      normalizePomodoroState({
        workDuration: 200,
        shortBreakDuration: -5,
        longBreakDuration: 0,
        mode: 'shortBreak',
        remainingSeconds: 9999,
        isRunning: true,
        timerHasStarted: true,
        completedFocusRounds: -4,
        completedPomodoros: 3,
        focusMinutes: 90,
        targetEndAt: 60_000,
      }),
    ).toEqual({
      workDuration: 60,
      shortBreakDuration: 1,
      longBreakDuration: 20,
      mode: 'shortBreak',
      remainingSeconds: 60,
      isRunning: true,
      timerHasStarted: true,
      completedFocusRounds: 0,
      completedPomodoros: 3,
      focusMinutes: 90,
      targetEndAt: 60_000,
    });

    vi.useRealTimers();
  });

  it('resolves unified focus completion into the next break round', () => {
    const completion = resolvePomodoroCompletion(createInitialPomodoroState());

    expect(completion.state.mode).toBe('shortBreak');
    expect(completion.state.remainingSeconds).toBe(10 * 60);
    expect(completion.state.completedFocusRounds).toBe(1);
    expect(completion.state.completedPomodoros).toBe(1);
    expect(completion.state.focusMinutes).toBe(45);
    expect(completion.event).toEqual({
      kind: 'focus-complete',
      nextMode: 'shortBreak',
      breakMinutes: 10,
      focusLogMinutes: 45,
    });
  });

  it('transitions break completion back into focus without logging minutes', () => {
    const initialState = {
      ...createInitialPomodoroState(),
      mode: 'shortBreak' as const,
      remainingSeconds: 10 * 60,
      completedFocusRounds: 2,
    };

    expect(resolvePomodoroCompletion(initialState)).toEqual({
      state: {
        ...initialState,
        mode: 'work',
        remainingSeconds: 45 * 60,
        isRunning: false,
      },
      event: {
        kind: 'break-complete',
        nextMode: 'work',
        breakMinutes: 45,
        focusLogMinutes: 0,
      },
    });
  });

  it('keeps remaining seconds in sync when adjusting the active mode while paused', () => {
    const initialState = createInitialPomodoroState();
    const nextState = adjustPomodoroDuration(initialState, 'work', true);

    expect(nextState.workDuration).toBe(46);
    expect(nextState.remainingSeconds).toBe(46 * 60);
  });

  it('starts the next round from focus mode', () => {
    const nextState = startNextPomodoroRound(
      {
        ...createInitialPomodoroState(),
        mode: 'longBreak',
        remainingSeconds: 20 * 60,
      },
      10_000,
    );

    expect(nextState.mode).toBe('work');
    expect(nextState.remainingSeconds).toBe(45 * 60);
    expect(nextState.timerHasStarted).toBe(true);
    expect(nextState.isRunning).toBe(true);
    expect(nextState.targetEndAt).toBe(10_000 + 45 * 60 * 1000);
  });

  it('reconciles a running timer from targetEndAt instead of tick counts', () => {
    const runningState = {
      ...createInitialPomodoroState(),
      isRunning: true,
      timerHasStarted: true,
      remainingSeconds: 45 * 60,
      targetEndAt: 45 * 60 * 1000,
    };

    const result = reconcilePomodoroState(runningState, 60_000);

    expect(result.event).toBeNull();
    expect(result.state.remainingSeconds).toBe(44 * 60);
    expect(result.state.targetEndAt).toBe(45 * 60 * 1000);
  });

  it('preserves the legacy tutor timer transition contract', () => {
    expect(resolveTutorTimerCompletion('focus', 0)).toEqual({
      timerState: 'shortBreak',
      remainingSeconds: 10 * 60,
      completedFocusRounds: 1,
      focusLogMinutes: 45,
    });
  });
});
