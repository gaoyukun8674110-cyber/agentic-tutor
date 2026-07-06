import type { ChangeEvent, RefObject } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Clock3,
  Download,
  FileText,
  History,
  Loader2,
  MessageSquareText,
  PanelLeftClose,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react';

import type { PromptProfile, StudyMaterial, TutorConversationSummary } from '../../utils/chatApi';
import type { Language, ThemeTokens } from '../../utils/settings';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import type { TimerState } from './types';

interface TutorSidebarProps {
  sidebarOpen: boolean;
  sidebarWidth: number;
  tokens: ThemeTokens;
  language: Language;
  profiles: PromptProfile[];
  selectedProfile: string;
  customPrompt: string;
  materials: StudyMaterial[];
  selectedMaterialIds: number[];
  isUploadingMaterial: boolean;
  materialError: string | null;
  loadError: string | null;
  historyLoadError: string | null;
  remainingSeconds: number;
  timerState: TimerState;
  isRunning: boolean;
  timerHasStarted: boolean;
  historySearchOpen: boolean;
  historySearchQuery: string;
  isSearchingHistory: boolean;
  historyItems: TutorConversationSummary[];
  activeConversationId: number | null;
  materialInputRef: RefObject<HTMLInputElement>;
  historySearchInputRef: RefObject<HTMLInputElement>;
  t: <T extends string>(zh: T, en: T) => T;
  onExit: () => void;
  onCollapse: () => void;
  onStartNewChat: () => void;
  onToggleHistorySearch: () => void;
  onCloseHistorySearch: () => void;
  onHistorySearchQueryChange: (query: string) => void;
  onSelectedProfileChange: (profileId: string) => void;
  onCustomPromptChange: (prompt: string) => void;
  onMaterialUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onToggleMaterialSelection: (materialId: number) => void;
  onToggleTimer: () => void;
  onResetTimer: () => void;
  onStartNextRound: () => void;
  onOpenHistoryItem: (id: number) => void;
  onExportHistoryItem: (id: number) => void;
  onRemoveHistoryItem: (id: number) => void;
}

function formatTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, '0');
  const seconds = (totalSeconds % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function formatHistoryMeta(item: TutorConversationSummary, language: Language) {
  const updatedAt = new Date(item.updated_at);
  const dateText = Number.isNaN(updatedAt.getTime())
    ? ''
    : updatedAt.toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });

  if (language === 'zh') return `${item.message_count} 条消息${dateText ? ` · ${dateText}` : ''}`;
  return `${item.message_count} messages${dateText ? ` · ${dateText}` : ''}`;
}

function sidebarCardStyle(tokens: ThemeTokens) {
  return {
    background: tokens.surfaceAccent,
    border: tokens.borderSubtle,
    boxShadow: tokens.shadowSoft,
  };
}

export function TutorSidebar({
  sidebarOpen,
  sidebarWidth,
  tokens,
  language,
  profiles,
  selectedProfile,
  customPrompt,
  materials,
  selectedMaterialIds,
  isUploadingMaterial,
  materialError,
  loadError,
  historyLoadError,
  remainingSeconds,
  timerState,
  isRunning,
  timerHasStarted,
  historySearchOpen,
  historySearchQuery,
  isSearchingHistory,
  historyItems,
  activeConversationId,
  materialInputRef,
  historySearchInputRef,
  t,
  onExit,
  onCollapse,
  onStartNewChat,
  onToggleHistorySearch,
  onCloseHistorySearch,
  onHistorySearchQueryChange,
  onSelectedProfileChange,
  onCustomPromptChange,
  onMaterialUpload,
  onToggleMaterialSelection,
  onToggleTimer,
  onResetTimer,
  onStartNextRound,
  onOpenHistoryItem,
  onExportHistoryItem,
  onRemoveHistoryItem,
}: TutorSidebarProps) {
  return (
    <aside
      className="flex-col"
      style={{
        position: 'fixed',
        top: 0,
        bottom: 0,
        left: 0,
        zIndex: 30,
        display: 'flex',
        width: sidebarOpen ? sidebarWidth : 0,
        height: '100vh',
        minHeight: 0,
        overflow: 'hidden',
        background: tokens.surfaceMuted,
        color: tokens.textPrimary,
        borderRight: sidebarOpen ? tokens.borderSubtle : '0',
        transition: 'width 180ms ease',
      }}
    >
      <div className="flex h-14 items-center justify-between px-4">
        <button
          onClick={onExit}
          className="flex h-9 w-9 items-center justify-center rounded-lg hover:bg-[var(--ai-hover-surface)]"
          aria-label={t('返回首页', 'Back')}
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <button
          onClick={onCollapse}
          className="flex h-9 w-9 items-center justify-center rounded-lg hover:bg-[var(--ai-hover-surface)]"
          aria-label={t('收起侧边栏', 'Collapse sidebar')}
        >
          <PanelLeftClose className="h-5 w-5" />
        </button>
      </div>

      <div className="space-y-1 px-3">
        <button
          onClick={onStartNewChat}
          className="flex h-11 w-full items-center gap-3 rounded-xl px-3 text-[15px] hover:bg-[var(--ai-hover-surface)]"
        >
          <Plus className="h-5 w-5" />
          {t('新学习会话', 'New study chat')}
        </button>
        <button
          onClick={onToggleHistorySearch}
          className="flex h-11 w-full items-center gap-3 rounded-xl px-3 text-[15px] hover:bg-[var(--ai-hover-surface)]"
          style={{ background: historySearchOpen ? tokens.hoverSurface : 'transparent' }}
        >
          <Search className="h-5 w-5" />
          {t('搜索记录', 'Search history')}
        </button>

        {historySearchOpen && (
          <div className="px-3 pb-2">
            <div
              className="flex h-9 items-center gap-2 rounded-md px-2"
              style={{
                background: tokens.inputSurface,
                border: tokens.borderSubtle,
                boxShadow: tokens.shadowSoft,
              }}
            >
              <Search className="h-4 w-4 shrink-0" style={{ color: tokens.textSecondary }} />
              <input
                ref={historySearchInputRef}
                value={historySearchQuery}
                onChange={(event) => onHistorySearchQueryChange(event.target.value)}
                placeholder={t('搜索标题、摘要或消息', 'Search title, summary, or messages')}
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--ai-placeholder-text)]"
                style={{ color: tokens.textPrimary }}
              />
              {isSearchingHistory ? (
                <Loader2
                  className="h-4 w-4 shrink-0 animate-spin"
                  style={{ color: tokens.textSecondary }}
                />
              ) : (
                <button
                  onClick={onCloseHistorySearch}
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md hover:bg-[var(--ai-hover-surface)]"
                  style={{ color: tokens.textSecondary }}
                  aria-label={t('关闭搜索', 'Close search')}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        )}

        <div className="pt-2">
          <div className="px-3 pb-1 text-xs" style={{ color: tokens.textMuted }}>
            {t('配置', 'Settings')}
          </div>
          <label
            className="block rounded-md px-3 py-2 transition-colors hover:bg-[var(--ai-hover-surface)]"
            style={sidebarCardStyle(tokens)}
          >
            <span
              className="mb-2 flex items-center gap-2 text-[13px]"
              style={{ color: tokens.textSecondary }}
            >
              <MessageSquareText className="h-4 w-4" />
              {t('教学策略', 'Profile')}
            </span>
            <Select value={selectedProfile} onValueChange={onSelectedProfileChange}>
              <SelectTrigger
                className="h-8 bg-[var(--ai-input-surface)] hover:bg-[var(--ai-input-surface)] focus:bg-[var(--ai-input-surface)]"
                style={{ color: tokens.textPrimary, border: tokens.borderSubtle }}
              >
                <SelectValue placeholder={t('选择策略', 'Choose profile')} />
              </SelectTrigger>
              <SelectContent>
                {profiles.map((profile) => (
                  <SelectItem key={profile.id} value={profile.id}>
                    {profile.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          {selectedProfile === 'custom' && (
            <textarea
              value={customPrompt}
              onChange={(event) => onCustomPromptChange(event.target.value)}
              placeholder={t('自定义系统提示词', 'Custom system prompt')}
              className="mx-3 mt-2 min-h-20 w-[calc(100%-24px)] resize-none rounded-lg px-3 py-2 text-sm outline-none placeholder:text-[var(--ai-placeholder-text)]"
              style={{
                background: tokens.inputSurface,
                border: tokens.borderSubtle,
                color: tokens.textPrimary,
              }}
            />
          )}

          <div
            className="mt-2 rounded-md px-3 py-2 transition-colors hover:bg-[var(--ai-hover-surface)]"
            style={sidebarCardStyle(tokens)}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span
                className="flex min-w-0 items-center gap-2 text-[13px]"
                style={{ color: tokens.textSecondary }}
              >
                <BookOpen className="h-4 w-4 shrink-0" />
                {t('学习资料', 'Study materials')}
              </span>
              <span className="text-xs" style={{ color: tokens.textMuted }}>
                {selectedMaterialIds.length}/{materials.length}
              </span>
            </div>
            <input
              ref={materialInputRef}
              type="file"
              accept=".txt,.md,.docx,.pdf,.epub"
              className="hidden"
              onChange={onMaterialUpload}
            />
            <button
              onClick={() => materialInputRef.current?.click()}
              disabled={isUploadingMaterial}
              className="flex h-8 w-full items-center justify-center gap-2 rounded-md border border-transparent text-sm hover:bg-[var(--ai-hover-surface)]"
              style={{
                background: tokens.inputSurface,
                boxShadow: tokens.shadowSoft,
                color: isUploadingMaterial ? tokens.disabledText : tokens.textPrimary,
              }}
            >
              {isUploadingMaterial ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              {isUploadingMaterial ? t('上传中', 'Uploading') : t('上传资料', 'Upload file')}
            </button>

            {materials.length > 0 ? (
              <div className="mt-2 max-h-36 space-y-1 overflow-y-auto">
                {materials.map((material) => (
                  <label
                    key={material.id}
                    className="flex min-w-0 items-center gap-2 rounded-md px-1 py-1 text-xs hover:bg-[var(--ai-hover-surface)]"
                    style={{ color: tokens.textSecondary }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedMaterialIds.includes(material.id)}
                      onChange={() => onToggleMaterialSelection(material.id)}
                      className="h-3.5 w-3.5 shrink-0"
                    />
                    <FileText
                      className="h-3.5 w-3.5 shrink-0"
                      style={{ color: tokens.textSecondary }}
                    />
                    <span className="min-w-0 flex-1 truncate">{material.filename}</span>
                    <span className="shrink-0" style={{ color: tokens.textMuted }}>
                      {material.chunk_count}
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-xs leading-5" style={{ color: tokens.textMuted }}>
                {t(
                  '支持 .txt / .md / .docx / .pdf / .epub',
                  'Supports .txt / .md / .docx / .pdf / .epub',
                )}
              </div>
            )}

            {materialError && (
              <div
                className="mt-2 flex gap-1.5 rounded-md px-2 py-1.5 text-xs"
                style={{ background: tokens.warningSoft, color: tokens.warning }}
              >
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                <span>{materialError}</span>
              </div>
            )}
          </div>

          <div
            className="mt-2 rounded-md px-3 py-2 transition-colors hover:bg-[var(--ai-hover-surface)]"
            style={sidebarCardStyle(tokens)}
          >
            <div className="mb-2 flex items-center justify-between">
              <span
                className="flex items-center gap-2 text-[13px]"
                style={{ color: tokens.textSecondary }}
              >
                <Clock3 className="h-4 w-4" />
                {t('番茄钟设置', 'Pomodoro')}
              </span>
              <span className="text-sm font-semibold tabular-nums">
                {formatTime(remainingSeconds)}
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={onToggleTimer}
                className="flex h-8 flex-1 items-center justify-center gap-1 rounded-md text-sm hover:bg-[var(--ai-hover-surface)]"
                style={{ background: tokens.inputSurface }}
              >
                {isRunning ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                {isRunning
                  ? t('暂停', 'Pause')
                  : timerHasStarted
                    ? t('继续', 'Resume')
                    : t('开始', 'Start')}
              </button>
              <button
                onClick={onResetTimer}
                className="flex h-8 w-9 items-center justify-center rounded-md hover:bg-[var(--ai-hover-surface)]"
                style={{ background: tokens.inputSurface }}
                aria-label={t('重置计时', 'Reset timer')}
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            </div>
            {timerState !== 'focus' && (
              <button
                onClick={onStartNextRound}
                className="mt-2 h-8 w-full rounded-md text-sm hover:bg-[var(--ai-hover-surface)]"
                style={{ background: tokens.inputSurface }}
              >
                {t('开始下一轮', 'Start next round')}
              </button>
            )}
          </div>

          {loadError && (
            <div
              className="mx-3 mt-2 flex gap-2 rounded-lg px-3 py-2 text-xs"
              style={{ background: tokens.warningSoft, color: tokens.warning }}
            >
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{loadError}</span>
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 px-3 pb-4" style={{ minHeight: 0, flex: 1, overflowY: 'auto' }}>
        <div
          className="mb-1 flex items-center gap-2 px-3 text-xs"
          style={{ color: tokens.textMuted }}
        >
          <History className="h-3.5 w-3.5" />
          {historySearchOpen && historySearchQuery.trim()
            ? t(`搜索结果 · ${historyItems.length}`, `Search results · ${historyItems.length}`)
            : t('往期学习训练记录', 'Past study sessions')}
        </div>
        {historyItems.length > 0 ? (
          <div className="space-y-1">
            {historyItems.map((item) => (
              <div
                key={item.id}
                className="group flex items-center gap-2 rounded-xl px-3 py-2 hover:bg-[var(--ai-hover-surface)]"
                style={{
                  background:
                    activeConversationId === item.id ? tokens.hoverSurface : 'transparent',
                }}
              >
                <button
                  onClick={() => onOpenHistoryItem(item.id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="block truncate text-[15px]">{item.title}</span>
                  <span className="block text-xs" style={{ color: tokens.textMuted }}>
                    {formatHistoryMeta(item, language)}
                  </span>
                </button>
                <button
                  onClick={() => onExportHistoryItem(item.id)}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md opacity-70 hover:bg-[var(--ai-hover-surface)] hover:opacity-100"
                  style={{ color: tokens.textSecondary }}
                  aria-label={t('导出记录', 'Export history item')}
                  title={t('导出记录', 'Export history item')}
                >
                  <Download className="h-4 w-4" />
                </button>
                <button
                  onClick={() => onRemoveHistoryItem(item.id)}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md opacity-70 hover:bg-[var(--ai-hover-surface)] hover:opacity-100"
                  style={{ color: tokens.textSecondary }}
                  aria-label={t('删除记录', 'Delete history item')}
                  title={t('删除记录', 'Delete history item')}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div
            className="rounded-xl px-3 py-3 text-sm leading-5"
            style={{ color: tokens.textMuted }}
          >
            {historyLoadError
              ? t(
                  '学习记录暂时无法同步，请确认后端服务已启动。',
                  'Study sessions are temporarily unavailable. Check that the backend is running.',
                )
              : historySearchOpen && historySearchQuery.trim()
                ? t('没有匹配的学习记录', 'No matching study sessions')
                : t('还没有学习记录', 'No study sessions yet')}
          </div>
        )}
      </div>
    </aside>
  );
}
