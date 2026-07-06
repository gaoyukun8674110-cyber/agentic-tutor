import { useCallback, type ElementType } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Brain, Target, Zap } from 'lucide-react';
import { PomodoroTimer } from '../components/PomodoroTimer';
import { StudyCalendar } from '../components/StudyCalendar';
import { StudyStats } from '../components/StudyStats';
import { TodayPlan } from '../components/TodayPlan';
import { TopNavbar } from '../components/TopNavbar';
import { Button } from '../components/ui/button';
import { useAuth } from '../auth/AuthContext';
import { fetchDashboardSummary } from '../utils/dashboardApi';
import { cardSurfaceStyle, primaryActionStyle } from '../utils/glassStyles';
import { useSettings } from '../utils/settings';

interface StatCard {
  icon: ElementType;
  label: string;
  value: string;
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { language, tokens, textStyle, t } = useSettings();
  const queryClient = useQueryClient();
  const { data: dashboardSummary } = useQuery({
    queryKey: ['dashboard-summary', user?.username],
    queryFn: ({ signal }) => fetchDashboardSummary({ signal }),
    enabled: Boolean(user),
    retry: false,
  });

  const refreshDashboard = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['dashboard-summary', user?.username] });
  }, [queryClient, user?.username]);

  const todayStats = dashboardSummary?.today;
  const focusMinutes = todayStats?.focus_minutes ?? 0;
  const completedPomodoros = todayStats?.completed_pomodoros ?? 0;
  const completedTasks = todayStats?.completed_tasks ?? 0;
  const totalTasks = todayStats?.total_tasks ?? 0;
  const streakDays = dashboardSummary?.streak_days ?? 0;
  const studyHours = focusMinutes / 60;
  const stats: StatCard[] = [
    {
      icon: BookOpen,
      label: t('今日学习时长', "Today's study time"),
      value:
        studyHours > 0
          ? language === 'zh'
            ? `${studyHours.toFixed(1)} 小时`
            : `${studyHours.toFixed(1)} h`
          : t('0 小时', '0 h'),
    },
    {
      icon: Target,
      label: t('完成任务', 'Tasks completed'),
      value: `${completedTasks} / ${totalTasks}`,
    },
    {
      icon: Brain,
      label: t('连续学习', 'Learning streak'),
      value:
        streakDays > 0
          ? language === 'zh'
            ? `${streakDays} 天`
            : `${streakDays} days`
          : t('0 天', '0 days'),
    },
  ];

  const cardStyle = cardSurfaceStyle(tokens);

  const dashboardShellClass = 'mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 xl:px-0';
  const dashboardGridClass = 'grid grid-cols-1 items-start gap-6 lg:grid-cols-3';

  const renderStatCard = (item: StatCard) => {
    const Icon = item.icon;

    return (
      <div className="min-h-[132px] rounded-2xl p-6 shadow-lg" style={cardStyle}>
        <div className="flex h-full items-center justify-between gap-5">
          <div>
            <p className="mb-2 text-sm font-medium" style={{ color: tokens.textSecondary }}>
              {item.label}
            </p>
            <p className="text-4xl font-bold tabular-nums" style={{ color: tokens.textSecondary }}>
              {item.value}
            </p>
          </div>
          <Icon
            className="h-10 w-10 shrink-0"
            style={{ color: tokens.textPrimary, opacity: 0.8 }}
          />
        </div>
      </div>
    );
  };

  return (
    <div
      className="relative min-h-screen overflow-hidden"
      style={{ ...textStyle, color: tokens.textPrimary }}
    >
      <div className="fixed inset-0" style={{ background: tokens.pageGradient }} />
      <div className="fixed inset-0" style={{ background: tokens.overlayGradient }} />
      <TopNavbar />

      <div className="relative">
        <div className={dashboardShellClass}>
          <div className={dashboardGridClass}>
            <section className="space-y-6">
              {renderStatCard(stats[0])}
              <PomodoroTimer
                userId={user?.username ?? ''}
                persistedCompletedPomodoros={completedPomodoros}
                persistedFocusMinutes={focusMinutes}
                onPomodoroLogged={refreshDashboard}
              />
            </section>

            <section className="space-y-6">
              {renderStatCard(stats[1])}
              <TodayPlan tasks={dashboardSummary?.tasks ?? []} onDataChange={refreshDashboard} />
            </section>

            <section className="space-y-6">
              {renderStatCard(stats[2])}
              <StudyStats
                focusMinutes={focusMinutes}
                completedPomodoros={completedPomodoros}
                completedTasks={completedTasks}
                totalTasks={totalTasks}
                weeklyData={dashboardSummary?.weekly_data ?? []}
              />
            </section>
          </div>

          <div className="mt-6 w-full">
            <Button
              onClick={() => navigate('/tutor')}
              className="w-full rounded-2xl py-6 font-medium shadow-lg transition-all duration-200"
              style={primaryActionStyle(tokens)}
            >
              <Zap className="h-5 w-5" />
              {t('进入今日学习', "Enter today's study")}
            </Button>

            <div className="mt-6">
              <StudyCalendar events={dashboardSummary?.calendar_events ?? []} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
