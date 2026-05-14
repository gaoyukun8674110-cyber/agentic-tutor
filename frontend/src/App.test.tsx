import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App';

vi.mock('./components/PomodoroTimer', () => ({
  PomodoroTimer: () => <div>pomodoro-timer</div>,
}));

vi.mock('./components/StudyCalendar', () => ({
  StudyCalendar: () => <div>study-calendar</div>,
}));

vi.mock('./components/StudyStats', () => ({
  StudyStats: () => <div>study-stats</div>,
}));

vi.mock('./components/TodayPlan', () => ({
  TodayPlan: () => <div>today-plan</div>,
}));

vi.mock('./components/TopNavbar', () => ({
  TopNavbar: () => <div>top-navbar</div>,
}));

vi.mock('./components/TutorChatWorkspace', () => ({
  TutorChatWorkspace: () => <div>tutor-workspace</div>,
}));

vi.mock('./auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'alice', email: null, created_at: 'now' },
    isBootstrapping: false,
    logout: vi.fn(),
  }),
}));

vi.mock('./utils/dashboardApi', () => ({
  fetchDashboardSummary: vi.fn().mockResolvedValue({
    today: {
      focus_minutes: 0,
      completed_pomodoros: 0,
      completed_tasks: 0,
      total_tasks: 0,
    },
    streak_days: 0,
    tasks: [],
    weekly_data: [],
    calendar_events: [],
  }),
}));

vi.mock('./utils/glassStyles', () => ({
  cardSurfaceStyle: () => ({}),
  primaryActionStyle: () => ({}),
}));

vi.mock('./utils/settings', () => ({
  useSettings: () => ({
    tokens: {
      textPrimary: '#111111',
      textSecondary: '#666666',
      pageGradient: '#ffffff',
      overlayGradient: '#ffffff',
    },
    textStyle: {},
    t: (zh: string, en: string) => en ?? zh,
  }),
}));

function renderApp(initialPath: string) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[initialPath]}
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('App routing', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the dashboard route at /', async () => {
    renderApp('/');

    expect(await screen.findByText('pomodoro-timer')).toBeInTheDocument();
    expect(screen.queryByText('tutor-workspace')).not.toBeInTheDocument();
  });

  it('renders the tutor route at /tutor', async () => {
    renderApp('/tutor');

    expect(await screen.findByText('tutor-workspace')).toBeInTheDocument();
    expect(screen.queryByText('pomodoro-timer')).not.toBeInTheDocument();
  });
});
