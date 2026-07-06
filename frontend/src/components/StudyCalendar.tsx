import { useMemo, useState } from 'react';
import { BookOpen, Calendar, ChevronLeft, ChevronRight, Clock } from 'lucide-react';

import type { DashboardCalendarEvent } from '../utils/dashboardApi';
import { formatLocalDateKey } from '../utils/dateKey';
import { useSettings } from '../utils/settings';

interface StudyCalendarProps {
  events?: DashboardCalendarEvent[];
}

const typeStyles = {
  task: { tone: 'success', icon: '✓', label: { zh: '任务', en: 'Task' } },
  chat: { tone: 'info', icon: 'AI', label: { zh: 'Tutor', en: 'Tutor' } },
  session: { tone: 'danger', icon: '●', label: { zh: '训练', en: 'Session' } },
} as const;

export function StudyCalendar({ events = [] }: StudyCalendarProps) {
  const [selectedDate, setSelectedDate] = useState<Date | null>(new Date());
  const [viewedMonth, setViewedMonth] = useState(() => {
    const today = new Date();
    return new Date(today.getFullYear(), today.getMonth(), 1);
  });
  const { language, tokens, t } = useSettings();

  const monthNames = useMemo(
    () =>
      language === 'zh'
        ? [
            '一月',
            '二月',
            '三月',
            '四月',
            '五月',
            '六月',
            '七月',
            '八月',
            '九月',
            '十月',
            '十一月',
            '十二月',
          ]
        : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
    [language],
  );

  const weekdays = useMemo(
    () =>
      language === 'zh'
        ? ['日', '一', '二', '三', '四', '五', '六']
        : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
    [language],
  );

  const selectedDateStr = selectedDate ? formatLocalDateKey(selectedDate) : '';
  const selectedEvents = events.filter((event) => event.date === selectedDateStr);

  const moveMonth = (offset: number) => {
    setViewedMonth((currentMonth) => {
      const nextMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + offset, 1);
      setSelectedDate((currentSelectedDate) => {
        const baseDate = currentSelectedDate ?? nextMonth;
        const lastDay = new Date(nextMonth.getFullYear(), nextMonth.getMonth() + 1, 0).getDate();
        return new Date(
          nextMonth.getFullYear(),
          nextMonth.getMonth(),
          Math.min(baseDate.getDate(), lastDay),
        );
      });
      return nextMonth;
    });
  };

  const renderCalendar = () => {
    const today = new Date();
    const currentMonth = viewedMonth.getMonth();
    const currentYear = viewedMonth.getFullYear();
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();

    const days = [];
    const accent = tokens.accentPrimary;
    const todayBg = tokens.accentPrimarySoft;
    const todayText = tokens.accentPrimary;

    for (let index = 0; index < startingDay; index += 1) {
      days.push(<div key={`empty-${index}`} className="h-8" />);
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const date = new Date(currentYear, currentMonth, day);
      const dateStr = formatLocalDateKey(date);
      const isSelected = selectedDate ? formatLocalDateKey(selectedDate) === dateStr : false;
      const isToday = formatLocalDateKey(today) === dateStr;
      const hasCourses = events.some((event) => event.date === dateStr);

      days.push(
        <button
          key={day}
          type="button"
          onClick={() => setSelectedDate(date)}
          className={`h-8 w-8 rounded-lg border text-sm font-medium transition-colors hover:bg-[var(--ai-hover-surface)] ${
            hasCourses ? 'relative' : ''
          }`}
          style={{
            background: isSelected ? accent : isToday ? todayBg : 'transparent',
            color: isSelected ? tokens.textInverted : isToday ? todayText : tokens.textPrimary,
            border: isSelected ? `1px solid ${accent}` : tokens.borderSoft,
          }}
        >
          {day}
          {hasCourses ? (
            <div
              className="absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full"
              style={{ background: tokens.accentSecondary }}
            />
          ) : null}
        </button>,
      );
    }

    return (
      <div className="p-4">
        <div className="mb-4 flex items-center justify-between gap-2">
          <button
            type="button"
            aria-label={t('上一个月', 'Previous month')}
            className="flex h-8 w-8 items-center justify-center rounded-lg border transition-colors"
            style={{
              background: tokens.surface,
              border: tokens.borderSoft,
              color: tokens.textPrimary,
            }}
            onClick={() => moveMonth(-1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <h3 className="font-medium" style={{ color: tokens.textPrimary }}>
            {currentYear} {monthNames[currentMonth]}
          </h3>
          <button
            type="button"
            aria-label={t('下一个月', 'Next month')}
            className="flex h-8 w-8 items-center justify-center rounded-lg border transition-colors"
            style={{
              background: tokens.surface,
              border: tokens.borderSoft,
              color: tokens.textPrimary,
            }}
            onClick={() => moveMonth(1)}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <div className="mb-2 grid grid-cols-7 gap-1">
          {weekdays.map((day) => (
            <div
              key={day}
              className="flex h-8 items-center justify-center text-xs font-medium"
              style={{ color: tokens.textSecondary }}
            >
              {day}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">{days}</div>
      </div>
    );
  };

  return (
    <div
      className="overflow-hidden rounded-2xl shadow-sm transition-all duration-300"
      style={{ background: tokens.surface, border: tokens.borderStrong, boxShadow: tokens.shadow }}
    >
      <div
        className="border-b p-6"
        style={{ background: tokens.surfaceMuted, borderBottom: tokens.borderSoft }}
      >
        <div className="flex items-center gap-2">
          <div
            className="rounded-xl p-2"
            style={{ background: tokens.surfaceAccent, border: tokens.borderSoft }}
          >
            <Calendar className="h-5 w-5" style={{ color: tokens.accentPrimary }} />
          </div>
          <h2 className="text-lg font-medium" style={{ color: tokens.accentPrimary }}>
            {t('日历', 'Calendar')}
          </h2>
        </div>
      </div>

      <div className="p-6">
        <div
          className="mb-4 rounded-2xl"
          style={{ background: tokens.surfaceMuted, border: tokens.borderSoft }}
        >
          {renderCalendar()}
        </div>

        {selectedDate ? (
          <div className="space-y-4">
            <div
              className="flex items-center gap-2 rounded-xl p-3"
              style={{ background: tokens.surfaceAccent, border: tokens.borderSoft }}
            >
              <BookOpen className="h-4 w-4" style={{ color: tokens.accentPrimary }} />
              <h4 className="font-medium" style={{ color: tokens.textPrimary }}>
                {selectedDate.toLocaleDateString(language === 'zh' ? 'zh-CN' : 'en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}{' '}
                {t('的课程安排', 'schedule')}
              </h4>
            </div>

            {selectedEvents.length > 0 ? (
              <div className="space-y-3">
                {selectedEvents.map((event, index) => {
                  const eventStyle =
                    typeStyles[event.type as keyof typeof typeStyles] || typeStyles.task;
                  const eventColor =
                    eventStyle.tone === 'success'
                      ? tokens.success
                      : eventStyle.tone === 'danger'
                        ? tokens.danger
                        : tokens.info;

                  return (
                    <div
                      key={event.id}
                      className="group rounded-2xl border p-4 transition-all duration-300 hover:scale-[1.02] hover:shadow-md"
                      style={{
                        animationDelay: `${index * 100}ms`,
                        background: tokens.surfaceMuted,
                        border: tokens.borderSoft,
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-start gap-3">
                          <div className="mt-1 text-sm font-semibold" style={{ color: eventColor }}>
                            {eventStyle.icon}
                          </div>
                          <div className="space-y-1">
                            <div className="font-medium" style={{ color: tokens.textPrimary }}>
                              {event.title}
                            </div>
                            <div
                              className="flex items-center gap-1 text-sm"
                              style={{ color: tokens.textSecondary }}
                            >
                              <Clock className="h-3 w-3" />
                              <span>{event.time || event.subtitle}</span>
                            </div>
                          </div>
                        </div>
                        <span
                          className="rounded-lg px-2 py-1 text-xs font-medium backdrop-blur-sm"
                          style={{
                            background: tokens.surfaceAccent,
                            border: tokens.borderSoft,
                            color: eventColor,
                          }}
                        >
                          {eventStyle.label[language]}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-8 text-center">
                <div
                  className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full border"
                  style={{ background: tokens.surfaceAccent, border: tokens.borderSoft }}
                >
                  <span className="text-2xl">🙂</span>
                </div>
                <p style={{ color: tokens.textSecondary }}>
                  {t('今天没有安排课程，好好休息吧。', 'No classes today. Enjoy the break!')}
                </p>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
