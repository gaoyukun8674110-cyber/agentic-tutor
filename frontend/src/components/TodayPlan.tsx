import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, Circle, Clock, Edit3, Plus, Save, Trash2, X } from 'lucide-react';

import {
  createDashboardTask,
  deleteDashboardTask,
  updateDashboardTask,
  type DashboardTask,
} from '../utils/dashboardApi';
import { clampDurationMinutes } from '../utils/duration';
import { cardSurfaceStyle, inputSurfaceStyle, panelSurfaceStyle } from '../utils/glassStyles';
import { useSettings } from '../utils/settings';
import { toastError } from '../utils/toast';

type Priority = 'high' | 'medium' | 'low';

interface TodayPlanStats {
  completedTasks: number;
  totalTasks: number;
  completedMinutes: number;
  totalMinutes: number;
}

interface TodayPlanProps {
  onStatsChange?: (stats: TodayPlanStats) => void;
  onDataChange?: () => void;
  tasks?: DashboardTask[];
}

const priorityStyles: Record<Priority, { label: string }> = {
  high: { label: 'High' },
  medium: { label: 'Medium' },
  low: { label: 'Low' },
};

export function TodayPlan({ onStatsChange, onDataChange, tasks = [] }: TodayPlanProps) {
  const [subject, setSubject] = useState('');
  const [taskText, setTaskText] = useState('');
  const [duration, setDuration] = useState(25);
  const [priority, setPriority] = useState<Priority>('medium');
  const [editingId, setEditingId] = useState<number | null>(null);
  const { tokens, t } = useSettings();

  const stats = useMemo(() => {
    const completed = tasks.filter((task) => task.completed);
    return {
      completedTasks: completed.length,
      totalTasks: tasks.length,
      completedMinutes: completed.reduce((sum, task) => sum + task.duration, 0),
      totalMinutes: tasks.reduce((sum, task) => sum + task.duration, 0),
    };
  }, [tasks]);

  useEffect(() => {
    onStatsChange?.(stats);
  }, [stats, onStatsChange]);

  const progressPercentage =
    stats.totalTasks > 0 ? (stats.completedTasks / stats.totalTasks) * 100 : 0;

  const resetForm = () => {
    setSubject('');
    setTaskText('');
    setDuration(25);
    setPriority('medium');
    setEditingId(null);
  };

  const saveTaskMutation = useMutation({
    mutationFn: async (task: {
      id?: number;
      subject: string;
      task: string;
      duration: number;
      priority: Priority;
    }) => {
      if (task.id) {
        return updateDashboardTask(task.id, {
          subject: task.subject,
          task: task.task,
          duration: task.duration,
          priority: task.priority,
        });
      }

      return createDashboardTask({
        subject: task.subject,
        task: task.task,
        duration: task.duration,
        priority: task.priority,
      });
    },
    onSuccess: () => {
      resetForm();
      onDataChange?.();
    },
    onError: (error) => {
      toastError(error, t('无法保存任务', 'Unable to save task'));
    },
  });

  const toggleTaskMutation = useMutation({
    mutationFn: async (task: DashboardTask) =>
      updateDashboardTask(task.id, {
        completed: !task.completed,
      }),
    onSuccess: () => {
      onDataChange?.();
    },
    onError: (error) => {
      toastError(error, t('无法更新任务', 'Unable to update task'));
    },
  });

  const deleteTaskMutation = useMutation({
    mutationFn: async (task: DashboardTask) => deleteDashboardTask(task.id),
    onSuccess: (_deleted, task) => {
      if (editingId === task.id) resetForm();
      onDataChange?.();
    },
    onError: (error) => {
      toastError(error, t('无法删除任务', 'Unable to delete task'));
    },
  });

  const isBusy =
    saveTaskMutation.isPending || toggleTaskMutation.isPending || deleteTaskMutation.isPending;

  const saveTask = () => {
    const cleanTask = taskText.trim();
    const cleanSubject = subject.trim() || 'Study';
    if (!cleanTask) return;

    saveTaskMutation.mutate({
      id: editingId ?? undefined,
      subject: cleanSubject,
      task: cleanTask,
      duration,
      priority,
    });
  };

  const editTask = (task: DashboardTask) => {
    setEditingId(task.id);
    setSubject(task.subject);
    setTaskText(task.task);
    setDuration(clampDurationMinutes(task.duration));
    setPriority(task.priority);
  };

  const toggleTask = (task: DashboardTask) => {
    toggleTaskMutation.mutate(task);
  };

  const deleteTask = (id: number) => {
    const task = tasks.find((item) => item.id === id);
    if (!task) return;
    deleteTaskMutation.mutate(task);
  };

  const cardStyle = cardSurfaceStyle(tokens);
  const panelStyle = panelSurfaceStyle(tokens);
  const fieldStyle = inputSurfaceStyle(tokens);

  const priorityColors: Record<Priority, string> = {
    high: tokens.danger,
    medium: tokens.accentPrimary,
    low: tokens.success,
  };

  return (
    <div
      className="h-full overflow-hidden rounded-2xl shadow-sm transition-all duration-300"
      style={cardStyle}
    >
      <div className="border-b p-6" style={panelStyle}>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-medium" style={{ color: tokens.accentSecondary }}>
              {t('今日学习计划', "Today's plan")}
            </h2>
            <p className="mt-1 text-sm" style={{ color: tokens.textSecondary }}>
              {t('为今天添加任务。', 'Add tasks for today.')}
            </p>
          </div>
          <div className="text-sm font-medium tabular-nums" style={{ color: tokens.textPrimary }}>
            {stats.completedTasks}/{stats.totalTasks} {t('任务', 'tasks')}
          </div>
        </div>

        <div
          className="mt-4 h-3 w-full rounded-full"
          style={{ background: tokens.surfaceAccent, border: tokens.borderSoft as string }}
        >
          <div
            className="h-3 rounded-full transition-all duration-300"
            style={{ width: `${progressPercentage}%`, background: tokens.progressGradient }}
          />
        </div>
      </div>

      <div className="space-y-5 p-6">
        <div className="grid grid-cols-1 gap-3 rounded-2xl p-4 sm:grid-cols-2" style={panelStyle}>
          <input
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            placeholder={t('科目', 'Subject')}
            className="rounded-xl px-3 py-2 text-sm outline-none placeholder:text-[var(--ai-placeholder-text)]"
            style={fieldStyle}
          />
          <input
            type="number"
            min={1}
            max={600}
            value={duration}
            onChange={(event) => setDuration(clampDurationMinutes(Number(event.target.value)))}
            className="rounded-xl px-3 py-2 text-sm outline-none placeholder:text-[var(--ai-placeholder-text)]"
            style={fieldStyle}
          />
          <input
            value={taskText}
            onChange={(event) => setTaskText(event.target.value)}
            placeholder={t('输入今日任务', "Enter today's task")}
            className="rounded-xl px-3 py-2 text-sm outline-none placeholder:text-[var(--ai-placeholder-text)] sm:col-span-2"
            style={fieldStyle}
          />
          <select
            value={priority}
            onChange={(event) => setPriority(event.target.value as Priority)}
            className="rounded-xl px-3 py-2 text-sm outline-none"
            style={fieldStyle}
          >
            <option value="high">{priorityStyles.high.label}</option>
            <option value="medium">{priorityStyles.medium.label}</option>
            <option value="low">{priorityStyles.low.label}</option>
          </select>
          <div className="flex gap-2">
            <button
              onClick={saveTask}
              disabled={!taskText.trim() || saveTaskMutation.isPending}
              className="flex h-10 flex-1 items-center justify-center gap-2 rounded-xl px-4 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: tokens.accentSecondary, color: tokens.textInverted }}
            >
              {editingId ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              {editingId ? t('保存', 'Save') : t('添加', 'Add')}
            </button>
            {editingId && (
              <button
                onClick={resetForm}
                className="flex h-10 w-10 items-center justify-center rounded-xl"
                style={panelStyle}
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {tasks.length === 0 ? (
          <div className="rounded-2xl p-8 text-center" style={panelStyle}>
            <p className="text-sm" style={{ color: tokens.textSecondary }}>
              {t('今天还没有任务。', 'No tasks yet')}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="group rounded-2xl border p-4 transition-all duration-200"
                style={panelStyle}
              >
                <div className="flex items-start gap-4">
                  <button
                    onClick={() => toggleTask(task)}
                    className="mt-1"
                    aria-label={t('切换任务完成状态', 'Toggle task')}
                    disabled={toggleTaskMutation.isPending}
                  >
                    {task.completed ? (
                      <CheckCircle2 className="h-6 w-6" style={{ color: tokens.success }} />
                    ) : (
                      <Circle
                        className="h-6 w-6 transition-colors"
                        style={{ color: tokens.textMuted }}
                      />
                    )}
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={task.completed ? 'line-through' : ''}
                        style={{ color: task.completed ? tokens.success : tokens.textPrimary }}
                      >
                        {task.subject}
                      </span>
                      <span
                        className="rounded-lg px-2 py-1 text-xs font-medium"
                        style={{
                          background: tokens.surface,
                          border: tokens.borderSoft,
                          color: priorityColors[task.priority],
                        }}
                      >
                        {priorityStyles[task.priority].label}
                      </span>
                    </div>
                    <p
                      className="mt-2 text-sm"
                      style={{
                        color: task.completed ? tokens.success : tokens.textSecondary,
                        textDecoration: task.completed ? 'line-through' : 'none',
                      }}
                    >
                      {task.task}
                    </p>
                    <div
                      className="mt-2 flex items-center gap-1 text-xs"
                      style={{ color: tokens.textSecondary }}
                    >
                      <Clock className="h-3 w-3" style={{ color: tokens.accentPrimary }} />
                      {task.duration}
                      {t('分钟', ' min')}
                    </div>
                  </div>

                  <div className="flex gap-2 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100">
                    <button
                      onClick={() => editTask(task)}
                      className="flex h-9 w-9 items-center justify-center rounded-xl"
                      style={panelStyle}
                      disabled={isBusy}
                    >
                      <Edit3 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => deleteTask(task.id)}
                      className="flex h-9 w-9 items-center justify-center rounded-xl"
                      style={panelStyle}
                      disabled={deleteTaskMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" style={{ color: tokens.danger }} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="rounded-2xl p-4" style={panelStyle}>
            <div style={{ color: tokens.success }}>{t('已完成', 'Done')}</div>
            <div
              className="mt-1 text-2xl font-semibold tabular-nums"
              style={{ color: tokens.textPrimary }}
            >
              {stats.completedMinutes}
              {t('分钟', ' min')}
            </div>
          </div>
          <div className="rounded-2xl p-4" style={panelStyle}>
            <div style={{ color: tokens.accentPrimary }}>{t('计划总计', 'Planned')}</div>
            <div
              className="mt-1 text-2xl font-semibold tabular-nums"
              style={{ color: tokens.textPrimary }}
            >
              {stats.totalMinutes}
              {t('分钟', ' min')}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
