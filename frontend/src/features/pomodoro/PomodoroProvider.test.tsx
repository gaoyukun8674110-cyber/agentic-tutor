import { act, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PomodoroProvider, usePomodoroController } from './PomodoroProvider';
import { createInitialPomodoroState } from '../../utils/pomodoro';
import { logDashboardPomodoro } from '../../utils/dashboardApi';

vi.mock('../../utils/dashboardApi', () => ({
  logDashboardPomodoro: vi.fn().mockResolvedValue(undefined),
}));

function Harness() {
  usePomodoroController();
  return null;
}

describe('PomodoroProvider', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('logs completed focus time when visibility reconciliation completes the timer', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    const runningState = {
      ...createInitialPomodoroState(),
      workDuration: 1,
      remainingSeconds: 1,
      isRunning: true,
      timerHasStarted: true,
      targetEndAt: 1000,
    };
    window.localStorage.setItem('ai-tutor-pomodoro-state-v1', JSON.stringify(runningState));
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });

    render(
      <PomodoroProvider>
        <Harness />
      </PomodoroProvider>,
    );

    vi.setSystemTime(1000);
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(logDashboardPomodoro).toHaveBeenCalledWith(1, 'work');
  });
});
