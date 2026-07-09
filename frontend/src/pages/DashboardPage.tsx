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
  const serif = "'Noto Serif SC', 'Songti SC', 'Georgia', serif";

  const dashboardShellClass = 'mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 xl:px-0';
  const dashboardGridClass = 'grid grid-cols-1 items-start gap-6 lg:grid-cols-3';

  const greeting = (() => {
    const hour = new Date().getHours();
    if (hour < 6) return t('夜深了', 'Late night');
    if (hour < 11) return t('卯时开卷', 'Morning study');
    if (hour < 14) return t('午间温故', 'Midday review');
    if (hour < 19) return t('午后进学', 'Afternoon study');
    return t('灯下夜读', 'Evening study');
  })();

  const renderStatCard = (item: StatCard) => {
    const Icon = item.icon;

    return (
      <div className="min-h-[132px] p-6" style={cardStyle}>
        <div className="flex h-full items-start justify-between gap-5">
          <div>
            <p
              className="mb-3 text-xs font-semibold uppercase"
              style={{ color: tokens.textMuted, letterSpacing: '0.14em' }}
            >
              {item.label}
            </p>
            <p
              className="tabular-nums"
              style={{
                color: tokens.textPrimary,
                fontFamily: serif,
                fontWeight: 700,
                fontSize: 32,
              }}
            >
              {item.value}
            </p>
          </div>
          <Icon className="h-6 w-6 shrink-0" style={{ color: tokens.accentPrimary }} />
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
          {/* 书院 hero —— 题眼 + agent 朱批 */}
          <section className="mb-8 grid grid-cols-1 items-end gap-8 lg:grid-cols-[1.3fr_1fr]">
            <div>
              <p
                className="mb-4 inline-flex items-center gap-2 text-xs font-semibold uppercase"
                style={{ color: tokens.accentPrimary, letterSpacing: '0.2em' }}
              >
                <span
                  aria-hidden
                  style={{
                    display: 'inline-block',
                    width: 22,
                    height: 1,
                    background: tokens.accentPrimary,
                  }}
                />
                {t('今日', 'Today')} · {greeting}
              </p>
              <h2
                className="mb-3"
                style={{
                  fontFamily: serif,
                  fontWeight: 700,
                  fontSize: 34,
                  lineHeight: 1.25,
                  letterSpacing: '0.01em',
                }}
              >
                {t('墨已研好，', 'The ink is ready — ')}
                <span style={{ color: tokens.accentPrimary }}>
                  {user?.username ?? t('学习者', 'let us')}
                </span>
                {t('，今日续起。', ' continue where you left off.')}
              </h2>
              <p className="max-w-xl text-sm" style={{ color: tokens.textSecondary }}>
                {t(
                  '我已复盘你近期的练习，为你备好今日该补的知识点。随时可以开卷。',
                  'I have reviewed your recent practice and prepared today’s focus. Open the book whenever you are ready.',
                )}
              </p>
            </div>

            {/* agent 诊断朱印卡 —— signature */}
            <aside className="relative p-6" style={cardStyle}>
              <span
                className="absolute grid place-items-center text-center"
                style={{
                  top: -14,
                  right: 20,
                  width: 52,
                  height: 52,
                  borderRadius: '50%',
                  border: '2px solid var(--ai-seal)',
                  color: 'var(--ai-seal)',
                  background: tokens.surface,
                  transform: 'rotate(-8deg)',
                  fontFamily: serif,
                  fontWeight: 700,
                  fontSize: 14,
                  lineHeight: 1.1,
                }}
                aria-hidden
              >
                {t('诊断\n已落', 'seen')
                  .split('\n')
                  .map((line, index) => (
                    <span key={index} style={{ display: 'block' }}>
                      {line}
                    </span>
                  ))}
              </span>
              <p
                className="mb-2 text-xs uppercase"
                style={{ color: tokens.textMuted, letterSpacing: '0.16em' }}
              >
                {t('诊断 · Diagnostician', 'Diagnostician')}
              </p>
              <p className="text-sm" style={{ color: tokens.textPrimary, lineHeight: 1.6 }}>
                {t('本周共专注 ', 'This week you focused for ')}
                <b style={{ color: 'var(--ai-seal)', fontWeight: 600 }}>
                  {studyHours > 0
                    ? language === 'zh'
                      ? `${studyHours.toFixed(1)} 小时`
                      : `${studyHours.toFixed(1)}h`
                    : t('尚未开始', 'not yet started')}
                </b>
                {streakDays > 0
                  ? t(
                      `，已连续 ${streakDays} 天。保持这个节奏。`,
                      `, ${streakDays} days in a row. Keep this rhythm.`,
                    )
                  : t('。今日迈出第一步。', '. Take the first step today.')}
              </p>
            </aside>
          </section>

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
              className="w-full py-6 font-medium transition-all duration-200"
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
