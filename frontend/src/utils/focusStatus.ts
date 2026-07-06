export type FocusTimerState = 'focus' | 'shortBreak' | 'longBreak';
export type FocusTone = 'active' | 'paused' | 'ready' | 'rest' | 'thinking';

export interface FocusStatusInput {
  timerState: FocusTimerState;
  isRunning: boolean;
  remainingSeconds: number;
  timerHasStarted: boolean;
  messageCount: number;
  userExchangeCount: number;
  selectedMaterialCount: number;
  activeMaterialHitCount: number;
  learningPhase?: string | null;
  isSending: boolean;
}

export interface LocalizedStatusText {
  zh: string;
  en: string;
}

export interface FocusStatus {
  focus: LocalizedStatusText & { tone: FocusTone };
  phase: LocalizedStatusText;
  detail: LocalizedStatusText;
}

const phaseLabels: Record<string, LocalizedStatusText> = {
  planning: { zh: '规划', en: 'Planning' },
  understanding: { zh: '理解', en: 'Understanding' },
  feynman: { zh: '费曼检查', en: 'Feynman check' },
  general: { zh: '待判断', en: 'Ready' },
};

function formatClock(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safeSeconds / 60)
    .toString()
    .padStart(2, '0');
  const seconds = (safeSeconds % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function exchangeDetail(count: number): LocalizedStatusText | null {
  if (count <= 0) return null;
  return {
    zh: `${count} 轮对话`,
    en: `${count} ${count === 1 ? 'exchange' : 'exchanges'}`,
  };
}

function materialHitDetail(count: number): LocalizedStatusText | null {
  if (count <= 0) return null;
  return {
    zh: `引用 ${count} 段资料`,
    en: `${count} material ${count === 1 ? 'hit' : 'hits'}`,
  };
}

function joinDetails(parts: Array<LocalizedStatusText | null>): LocalizedStatusText {
  const present = parts.filter((part): part is LocalizedStatusText => Boolean(part));
  return {
    zh: present.map((part) => part.zh).join(' · '),
    en: present.map((part) => part.en).join(' · '),
  };
}

export function resolveFocusStatus(input: FocusStatusInput): FocusStatus {
  const normalizedPhase =
    input.learningPhase && phaseLabels[input.learningPhase] ? input.learningPhase : 'general';
  const phase =
    input.messageCount === 0 && !input.timerHasStarted
      ? { zh: '待开始', en: 'Ready' }
      : phaseLabels[normalizedPhase];

  const timeLeft = {
    zh: `剩余 ${formatClock(input.remainingSeconds)}`,
    en: `${formatClock(input.remainingSeconds)} left`,
  };
  const activityDetails = joinDetails([
    timeLeft,
    exchangeDetail(input.userExchangeCount),
    materialHitDetail(input.activeMaterialHitCount),
  ]);

  if (input.isSending) {
    return {
      focus: { zh: 'AI 生成中', en: 'AI responding', tone: 'thinking' },
      phase,
      detail: joinDetails([
        { zh: '等待 Tutor 回复', en: 'Waiting for tutor reply' },
        exchangeDetail(input.userExchangeCount),
      ]),
    };
  }

  if (input.timerState === 'shortBreak') {
    return {
      focus: { zh: '短休息', en: 'Short break', tone: 'rest' },
      phase,
      detail: activityDetails,
    };
  }

  if (input.timerState === 'longBreak') {
    return {
      focus: { zh: '长休息', en: 'Long break', tone: 'rest' },
      phase,
      detail: activityDetails,
    };
  }

  if (input.isRunning) {
    return {
      focus: { zh: '专注中', en: 'Focusing', tone: 'active' },
      phase,
      detail: activityDetails,
    };
  }

  if (input.timerHasStarted) {
    return {
      focus: { zh: '已暂停', en: 'Paused', tone: 'paused' },
      phase,
      detail: activityDetails,
    };
  }

  if (input.messageCount > 0) {
    return {
      focus: { zh: '对话训练中', en: 'Training chat', tone: 'active' },
      phase,
      detail: joinDetails([
        exchangeDetail(input.userExchangeCount),
        materialHitDetail(input.activeMaterialHitCount),
      ]),
    };
  }

  if (input.selectedMaterialCount > 0) {
    return {
      focus: { zh: '资料就绪', en: 'Materials ready', tone: 'ready' },
      phase,
      detail: {
        zh: `已选择 ${input.selectedMaterialCount} 份资料`,
        en: `${input.selectedMaterialCount} ${input.selectedMaterialCount === 1 ? 'material' : 'materials'} selected`,
      },
    };
  }

  return {
    focus: { zh: '待开始', en: 'Ready', tone: 'ready' },
    phase,
    detail: { zh: '还没有开始本轮学习', en: 'No active study session yet' },
  };
}
