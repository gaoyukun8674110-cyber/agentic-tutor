import { useEffect, useRef, useState } from 'react';
import { Brain, Coffee, Minus, Pause, Play, Plus, RotateCcw, Settings, Target } from 'lucide-react';

import { usePomodoroController } from '../features/pomodoro/PomodoroProvider';
import { cardSurfaceStyle, panelSurfaceStyle } from '../utils/glassStyles';
import { type PomodoroMode } from '../utils/pomodoro';
import { useSettings } from '../utils/settings';

type TimerMode = PomodoroMode;

interface PomodoroStats {
  completedPomodoros: number;
  focusMinutes: number;
}

interface PomodoroTimerProps {
  onStatsChange?: (stats: PomodoroStats) => void;
  onPomodoroLogged?: () => void;
  userId?: string;
  persistedCompletedPomodoros?: number;
  persistedFocusMinutes?: number;
}

const modeCopy = {
  work: {
    zh: '专注',
    en: 'Focus',
    icon: Brain,
  },
  shortBreak: {
    zh: '短休息',
    en: 'Short break',
    icon: Coffee,
  },
  longBreak: {
    zh: '长休息',
    en: 'Long break',
    icon: Target,
  },
} satisfies Record<TimerMode, { zh: string; en: string; icon: typeof Brain }>;

export function PomodoroTimer({
  onStatsChange,
  onPomodoroLogged,
  persistedCompletedPomodoros,
  persistedFocusMinutes,
}: PomodoroTimerProps) {
  const [showSettings, setShowSettings] = useState(false);
  const { state, logVersion, toggleTimer, resetTimer, switchMode, adjustDuration } =
    usePomodoroController();
  const { language, tokens, t } = useSettings();
  const settingsPanelRef = useRef<HTMLDivElement | null>(null);
  const settingsToggleRef = useRef<HTMLButtonElement | null>(null);
  const lastSeenLogVersionRef = useRef(logVersion);

  useEffect(() => {
    onStatsChange?.({
      completedPomodoros: state.completedPomodoros,
      focusMinutes: state.focusMinutes,
    });
  }, [onStatsChange, state.completedPomodoros, state.focusMinutes]);

  useEffect(() => {
    if (logVersion === lastSeenLogVersionRef.current) return;
    lastSeenLogVersionRef.current = logVersion;
    onPomodoroLogged?.();
  }, [logVersion, onPomodoroLogged]);

  useEffect(() => {
    if (!showSettings) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (settingsPanelRef.current?.contains(target)) return;
      if (settingsToggleRef.current?.contains(target)) return;
      setShowSettings(false);
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [showSettings]);

  const getCurrentDuration = () => {
    if (state.mode === 'work') return state.workDuration * 60;
    if (state.mode === 'shortBreak') return state.shortBreakDuration * 60;
    return state.longBreakDuration * 60;
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const currentDuration = getCurrentDuration();
  const progress =
    currentDuration > 0 ? ((currentDuration - state.remainingSeconds) / currentDuration) * 100 : 0;
  const currentConfig = modeCopy[state.mode];
  const Icon = currentConfig.icon;
  const modeColor =
    state.mode === 'work'
      ? tokens.accentSecondary
      : state.mode === 'shortBreak'
        ? tokens.success
        : tokens.accentPrimary;
  const displayedCompletedPomodoros = Math.max(
    persistedCompletedPomodoros ?? 0,
    state.completedPomodoros,
  );
  const displayedFocusMinutes = Math.max(persistedFocusMinutes ?? 0, state.focusMinutes);

  const cardStyle = cardSurfaceStyle(tokens);

  const headerStyle = {
    background:
      state.mode === 'work'
        ? tokens.accentSecondarySoft
        : state.mode === 'shortBreak'
          ? tokens.successSoft
          : tokens.accentPrimarySoft,
    backdropFilter: 'blur(14px)',
    borderBottom: tokens.borderSoft,
  };

  const controlStyle = panelSurfaceStyle(tokens);

  return (
    <div
      className="h-full overflow-hidden rounded-2xl shadow-sm transition-all duration-300"
      style={cardStyle}
    >
      <div className="border-b p-6" style={headerStyle}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="rounded-xl p-2" style={controlStyle}>
              <Icon className="h-5 w-5" style={{ color: modeColor }} />
            </div>
            <h2 className="text-lg font-medium" style={{ color: modeColor }}>
              {t('番茄钟', 'Pomodoro')}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="flex items-center gap-1 rounded-full px-3 py-1 text-sm font-medium"
              style={controlStyle}
            >
              <span style={{ color: tokens.textSecondary }}>{t('轮次', 'Rounds')}</span>
              <span style={{ color: tokens.textPrimary }}>{displayedCompletedPomodoros}</span>
            </div>
            <button
              ref={settingsToggleRef}
              onClick={() => setShowSettings((prev) => !prev)}
              className="rounded-xl p-2 transition-all"
              style={controlStyle}
              aria-label={t('时长设置', 'Duration settings')}
            >
              <Settings className="h-4 w-4" style={{ color: tokens.textPrimary }} />
            </button>
          </div>
        </div>
      </div>

      <div className="p-6">
        {showSettings && (
          <div
            ref={settingsPanelRef}
            className="mb-6 space-y-3 rounded-2xl p-4"
            style={controlStyle}
          >
            <h3 className="mb-3 text-sm font-medium" style={{ color: tokens.textPrimary }}>
              {t('时长设置', 'Durations')}
            </h3>

            {(
              [
                { key: 'work', label: t('专注时长', 'Focus time') },
                { key: 'shortBreak', label: t('短休息', 'Short break') },
                { key: 'longBreak', label: t('长休息', 'Long break') },
              ] as { key: TimerMode; label: string }[]
            ).map((item) => (
              <div key={item.key} className="flex items-center justify-between gap-3">
                <span className="text-sm" style={{ color: tokens.textSecondary }}>
                  {item.label}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => adjustDuration(item.key, false)}
                    disabled={
                      (item.key === 'work' && state.workDuration <= 1) ||
                      (item.key === 'shortBreak' && state.shortBreakDuration <= 1) ||
                      (item.key === 'longBreak' && state.longBreakDuration <= 1)
                    }
                    className="rounded-lg p-1 disabled:cursor-not-allowed disabled:opacity-50"
                    style={controlStyle}
                    aria-label={t('减少时长', 'Decrease duration')}
                  >
                    <Minus className="h-4 w-4" style={{ color: tokens.textSecondary }} />
                  </button>
                  <span
                    className="w-16 rounded-lg py-1 text-center text-sm font-medium"
                    style={{ ...controlStyle, color: tokens.textPrimary }}
                  >
                    {item.key === 'work'
                      ? state.workDuration
                      : item.key === 'shortBreak'
                        ? state.shortBreakDuration
                        : state.longBreakDuration}
                    {t('分', 'm')}
                  </span>
                  <button
                    onClick={() => adjustDuration(item.key, true)}
                    disabled={
                      (item.key === 'work' && state.workDuration >= 60) ||
                      (item.key === 'shortBreak' && state.shortBreakDuration >= 30) ||
                      (item.key === 'longBreak' && state.longBreakDuration >= 60)
                    }
                    className="rounded-lg p-1 disabled:cursor-not-allowed disabled:opacity-50"
                    style={controlStyle}
                    aria-label={t('增加时长', 'Increase duration')}
                  >
                    <Plus className="h-4 w-4" style={{ color: tokens.textSecondary }} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mb-6 flex gap-2">
          {(['work', 'shortBreak', 'longBreak'] as TimerMode[]).map((item) => (
            <button
              key={item}
              onClick={() => switchMode(item)}
              className="flex-1 rounded-xl border px-3 py-2 text-sm font-medium transition-all"
              style={{
                border: state.mode === item ? tokens.borderStrong : tokens.borderSoft,
                background: state.mode === item ? tokens.surface : tokens.surfaceMuted,
                color:
                  state.mode === item
                    ? item === 'work'
                      ? tokens.accentSecondary
                      : item === 'shortBreak'
                        ? tokens.success
                        : tokens.accentPrimary
                    : tokens.textSecondary,
              }}
            >
              {modeCopy[item][language]}
            </button>
          ))}
        </div>

        <div className="relative mb-6">
          <div className="relative mx-auto h-48 w-48">
            <svg className="h-full w-full -rotate-90 transform">
              <circle
                cx="96"
                cy="96"
                r="88"
                stroke="currentColor"
                strokeWidth="8"
                fill="none"
                className="text-gray-300/30"
              />
              <circle
                cx="96"
                cy="96"
                r="88"
                stroke="currentColor"
                strokeWidth="8"
                fill="none"
                strokeDasharray={`${2 * Math.PI * 88}`}
                strokeDashoffset={`${2 * Math.PI * 88 * (1 - progress / 100)}`}
                className="transition-all"
                style={{
                  transition: 'stroke-dashoffset 1s linear',
                  stroke: modeColor,
                  filter: 'drop-shadow(0 0 8px currentColor)',
                }}
              />
            </svg>

            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div
                className="text-4xl font-bold tabular-nums"
                style={{ color: tokens.textPrimary }}
              >
                {formatTime(state.remainingSeconds)}
              </div>
              <div className="mt-1 text-sm" style={{ color: tokens.textSecondary }}>
                {modeCopy[state.mode][language]}
              </div>
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={toggleTimer}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-r py-3 font-medium transition-all"
            style={{
              background: state.mode === 'work' ? tokens.primaryActionGradient : modeColor,
              border: tokens.borderSoft,
              color: tokens.textInverted,
            }}
          >
            {state.isRunning ? (
              <>
                <Pause className="h-5 w-5" />
                {t('暂停', 'Pause')}
              </>
            ) : (
              <>
                <Play className="h-5 w-5" />
                {t('开始', 'Start')}
              </>
            )}
          </button>
          <button
            onClick={resetTimer}
            className="rounded-xl px-4 py-3 transition-all"
            style={controlStyle}
          >
            <RotateCcw className="h-5 w-5" style={{ color: tokens.textSecondary }} />
          </button>
        </div>

        <div
          className="mt-4 rounded-2xl p-3"
          style={{
            ...controlStyle,
            background:
              state.mode === 'work'
                ? tokens.accentSecondarySoft
                : state.mode === 'shortBreak'
                  ? tokens.successSoft
                  : tokens.accentPrimarySoft,
          }}
        >
          <p className="text-center text-sm tabular-nums" style={{ color: tokens.textSecondary }}>
            {t(
              `今日专注 ${displayedFocusMinutes} 分钟`,
              `${displayedFocusMinutes} focused minutes today`,
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
