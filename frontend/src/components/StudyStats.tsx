import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useMemo } from 'react';
import { BookOpen, Clock, Target, TimerReset, TrendingUp } from 'lucide-react';
import type { DashboardWeekDay } from '../utils/dashboardApi';
import { cardSurfaceStyle, panelSurfaceStyle } from '../utils/glassStyles';
import { parseLocalDateKey } from '../utils/dateKey';
import { useSettings } from '../utils/settings';

interface StudyStatsProps {
  focusMinutes?: number;
  completedPomodoros?: number;
  completedTasks?: number;
  totalTasks?: number;
  weeklyData?: DashboardWeekDay[];
}

const dayKeys = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;
type DayKey = (typeof dayKeys)[number];

const dayNames: Record<'zh' | 'en', Record<DayKey, string>> = {
  zh: { mon: '周一', tue: '周二', wed: '周三', thu: '周四', fri: '周五', sat: '周六', sun: '周日' },
  en: { mon: 'Mon', tue: 'Tue', wed: 'Wed', thu: 'Thu', fri: 'Fri', sat: 'Sat', sun: 'Sun' },
};

const jsDayToKey: Record<number, DayKey> = {
  0: 'sun',
  1: 'mon',
  2: 'tue',
  3: 'wed',
  4: 'thu',
  5: 'fri',
  6: 'sat',
};

export function StudyStats({
  focusMinutes = 0,
  completedPomodoros = 0,
  completedTasks = 0,
  totalTasks = 0,
  weeklyData: persistedWeeklyData = [],
}: StudyStatsProps) {
  const { language, tokens, t } = useSettings();
  const todayKey = jsDayToKey[new Date().getDay()];
  const todayHours = Number((focusMinutes / 60).toFixed(2));

  const weeklyData = useMemo(
    () =>
      persistedWeeklyData.length > 0
        ? persistedWeeklyData.map((item) => {
            const parsedDate = parseLocalDateKey(item.date);
            const dayKey = jsDayToKey[parsedDate.getDay()] || todayKey;
            return {
              key: item.date,
              day: dayNames[language][dayKey],
              hours: item.hours,
              tasks: item.tasks,
            };
          })
        : dayKeys.map((key) => ({
            key,
            day: dayNames[language][key],
            hours: key === todayKey ? todayHours : 0,
            tasks: key === todayKey ? completedTasks : 0,
          })),
    [completedTasks, language, persistedWeeklyData, todayHours, todayKey],
  );

  const totalHours = weeklyData.reduce((sum, day) => sum + day.hours, 0);
  const avgHours = totalHours > 0 ? totalHours / weeklyData.length : 0;

  const cardStyle = cardSurfaceStyle(tokens);

  const sectionStyle = panelSurfaceStyle(tokens);

  const summaryCards = [
    {
      icon: Clock,
      label: t('本周总时长', 'Total hours'),
      value: `${totalHours.toFixed(1)}h`,
      color: tokens.accentPrimary,
    },
    {
      icon: BookOpen,
      label: t('日均学习', 'Daily avg'),
      value: `${avgHours.toFixed(1)}h`,
      color: tokens.accentSecondary,
    },
    {
      icon: Target,
      label: t('完成任务', 'Tasks done'),
      value: `${completedTasks}/${totalTasks}`,
      color: tokens.danger,
    },
    {
      icon: TimerReset,
      label: t('番茄轮次', 'Pomodoros'),
      value: `${completedPomodoros}`,
      color: tokens.success,
    },
  ];

  return (
    <div
      className="rounded-2xl overflow-hidden shadow-sm transition-all duration-300"
      style={cardStyle}
    >
      <div className="p-6 border-b" style={sectionStyle}>
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl" style={sectionStyle}>
            <TrendingUp className="h-5 w-5" style={{ color: tokens.accentPrimary }} />
          </div>
          <h2 className="text-lg font-medium" style={{ color: tokens.accentPrimary }}>
            {t('学习统计', 'Study stats')}
          </h2>
        </div>
      </div>

      <div className="p-6 space-y-6">
        <div className="grid grid-cols-2 gap-3">
          {summaryCards.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} className="p-4 rounded-2xl" style={sectionStyle}>
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="h-4 w-4" style={{ color: item.color }} />
                  <span className="text-xs" style={{ color: item.color }}>
                    {item.label}
                  </span>
                </div>
                <p className="text-2xl font-bold tabular-nums" style={{ color: item.color }}>
                  {item.value}
                </p>
              </div>
            );
          })}
        </div>

        <div className="rounded-2xl p-4" style={sectionStyle}>
          <h3
            className="text-sm font-medium mb-4 flex items-center gap-2"
            style={{ color: tokens.textPrimary }}
          >
            <Clock className="h-4 w-4" style={{ color: tokens.accentPrimary }} />
            {t('本周学习时长趋势', 'Weekly time')}
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={weeklyData}>
              <CartesianGrid strokeDasharray="3 3" stroke={tokens.chartGrid} opacity={0.25} />
              <XAxis
                dataKey="day"
                tick={{ fill: tokens.textSecondary, fontSize: 12 }}
                axisLine={{ stroke: tokens.chartAxis, opacity: 0.25 }}
              />
              <YAxis
                tick={{ fill: tokens.textSecondary, fontSize: 12 }}
                axisLine={{ stroke: tokens.chartAxis, opacity: 0.25 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: tokens.chartTooltipBg,
                  backdropFilter: 'blur(10px)',
                  border: tokens.borderSoft,
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
              />
              <Line
                type="monotone"
                dataKey="hours"
                stroke={tokens.accentPrimary}
                strokeWidth={3}
                dot={{ fill: tokens.accentPrimary, r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-2xl p-4" style={sectionStyle}>
          <h3
            className="text-sm font-medium mb-4 flex items-center gap-2"
            style={{ color: tokens.textPrimary }}
          >
            <Target className="h-4 w-4" style={{ color: tokens.accentSecondary }} />
            {t('每日任务完成数', 'Tasks per day')}
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={weeklyData}>
              <CartesianGrid strokeDasharray="3 3" stroke={tokens.chartGrid} opacity={0.25} />
              <XAxis
                dataKey="day"
                tick={{ fill: tokens.textSecondary, fontSize: 12 }}
                axisLine={{ stroke: tokens.chartAxis, opacity: 0.25 }}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fill: tokens.textSecondary, fontSize: 12 }}
                axisLine={{ stroke: tokens.chartAxis, opacity: 0.25 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: tokens.chartTooltipBg,
                  backdropFilter: 'blur(10px)',
                  border: tokens.borderSoft,
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="tasks" fill="url(#colorTasks)" radius={[8, 8, 0, 0]} />
              <defs>
                <linearGradient id="colorTasks" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={tokens.accentSecondary} stopOpacity={0.75} />
                  <stop offset="100%" stopColor={tokens.accentSecondary} stopOpacity={0.2} />
                </linearGradient>
              </defs>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
