import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, PanelLeftOpen } from 'lucide-react';

import { useTutorChat } from '../features/tutor/useTutorChat';
import { useTutorHistory } from '../features/tutor/useTutorHistory';
import { useTutorMaterials } from '../features/tutor/useTutorMaterials';
import { resolveFocusStatus, type FocusTone } from '../utils/focusStatus';
import { statusPanelStyle } from '../utils/glassStyles';
import { useSettings, type ThemeTokens } from '../utils/settings';
import { TutorComposer } from './tutor/TutorComposer';
import { TutorMessageList } from './tutor/TutorMessageList';
import { TutorSidebar } from './tutor/TutorSidebar';
import { useTutorTimer } from './tutor/useTutorTimer';

interface TutorChatWorkspaceProps {
  trainingMode: string;
  onExit: () => void;
  onConfigureModel?: () => void;
  onPomodoroLogged?: () => void;
}

const quickActions = [
  { zh: '给我一个提示', en: 'Give me a hint', profile: 'three_stage' },
  { zh: '换一种方式解释', en: 'Explain differently', profile: 'three_stage' },
  { zh: '检查我的答案', en: 'Check my answer', profile: 'three_stage' },
  { zh: '安排下一步', en: 'Plan next step', profile: 'three_stage' },
];

function getFocusToneStyle(tokens: ThemeTokens, tone: FocusTone) {
  return {
    active: {
      background: tokens.successSoft,
      borderColor: tokens.success,
      color: tokens.success,
      dot: tokens.success,
    },
    paused: {
      background: tokens.warningSoft,
      borderColor: tokens.warning,
      color: tokens.warning,
      dot: tokens.warning,
    },
    ready: {
      background: tokens.surfaceMuted,
      borderColor: 'var(--ai-border-subtle)',
      color: tokens.textSecondary,
      dot: tokens.textSecondary,
    },
    rest: {
      background: tokens.infoSoft,
      borderColor: tokens.info,
      color: tokens.info,
      dot: tokens.info,
    },
    thinking: {
      background: tokens.accentPrimarySoft,
      borderColor: tokens.accentPrimary,
      color: tokens.accentPrimary,
      dot: tokens.accentPrimary,
    },
  }[tone];
}

export function TutorChatWorkspace({
  trainingMode,
  onExit,
  onConfigureModel,
  onPomodoroLogged,
}: TutorChatWorkspaceProps) {
  const { language, textStyle, tokens, t } = useSettings();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isPinnedToBottom, setIsPinnedToBottom] = useState(true);
  const appendTimerMessageRef = useRef<(content: string) => void>(() => undefined);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const materialInputRef = useRef<HTMLInputElement>(null);
  const historySearchInputRef = useRef<HTMLInputElement>(null);

  const materials = useTutorMaterials();
  const {
    remainingSeconds,
    timerState,
    isRunning,
    timerHasStarted,
    resetTimer,
    startNextRound,
    toggleTimer,
  } = useTutorTimer({
    language,
    onPomodoroLogged,
    onTimerMessage: (content) => appendTimerMessageRef.current(content),
  });
  const chat = useTutorChat({
    language,
    t,
    trainingMode,
    timerState,
    remainingSeconds,
    selectedMaterialIds: materials.selectedMaterialIds,
  });
  const history = useTutorHistory({
    activeConversationId: chat.activeConversationId,
    onConversationOpened: chat.applyConversation,
    onActiveConversationRemoved: chat.startNewChat,
  });

  const focusStatus = useMemo(
    () =>
      resolveFocusStatus({
        timerState,
        isRunning,
        remainingSeconds,
        timerHasStarted,
        messageCount: chat.messages.filter((message) => message.label !== 'Timer').length,
        userExchangeCount: chat.visibleExchangeCount,
        selectedMaterialCount: materials.selectedMaterialIds.length,
        activeMaterialHitCount: chat.activeMaterialContext?.chunks?.length ?? 0,
        learningPhase: chat.learningPhase,
        isSending: chat.isSending,
      }),
    [
      chat.activeMaterialContext,
      chat.isSending,
      chat.learningPhase,
      chat.messages,
      chat.visibleExchangeCount,
      isRunning,
      materials.selectedMaterialIds.length,
      remainingSeconds,
      timerHasStarted,
      timerState,
    ],
  );

  const modeLabel = useMemo(() => {
    if (trainingMode === 'light') return language === 'zh' ? '轻度学习' : 'Light study';
    if (trainingMode === 'break') return language === 'zh' ? '休息恢复' : 'Rest reset';
    return language === 'zh' ? '深度专注' : 'Deep focus';
  }, [trainingMode, language]);
  const focusText = focusStatus.focus[language];
  const phaseText = focusStatus.phase[language];
  const detailText = focusStatus.detail[language];
  const loadError = chat.loadError ?? history.loadError ?? materials.loadError;
  const historyLoadError = history.loadError;
  const focusToneStyle = getFocusToneStyle(tokens, focusStatus.focus.tone);

  useEffect(() => {
    if (!isPinnedToBottom) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [chat.activeMaterialContext, chat.messages, isPinnedToBottom]);

  useEffect(() => {
    appendTimerMessageRef.current = chat.appendTimerMessage;
  }, [chat.appendTimerMessage]);

  useEffect(() => {
    if (!history.historySearchOpen) return;
    historySearchInputRef.current?.focus();
  }, [history.historySearchOpen]);

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;

    const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    setIsPinnedToBottom(distanceToBottom < 120);
  };

  const sidebarWidth = 240;

  const renderConversationNotice = () => {
    if (chat.visibleExchangeCount < 10) return null;

    const shouldStartNew = chat.visibleExchangeCount >= 15;
    return (
      <div
        className="mb-3 flex flex-col gap-2 rounded-2xl border px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
        style={{
          background: shouldStartNew ? tokens.accentSecondarySoft : tokens.warningSoft,
          borderColor: shouldStartNew ? tokens.accentSecondary : tokens.warning,
          color: shouldStartNew ? tokens.accentSecondary : tokens.warning,
        }}
      >
        <div className="flex min-w-0 items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {shouldStartNew
              ? t(
                  '已经达到 15 轮，系统已生成学习摘要。建议开启新学习会话，后续只携带摘要和最近关键上下文。',
                  '15 exchanges reached. A study summary is ready. Start a new chat to carry only the summary and recent key context.',
                )
              : t(
                  '这段对话已经超过 10 轮，可以继续，但建议准备开启新学习会话以节省 token。',
                  'This chat has passed 10 exchanges. You can continue, but consider starting a new chat to save tokens.',
                )}
          </span>
        </div>
        {shouldStartNew && (
          <button
            onClick={chat.startNewChat}
            className="shrink-0 rounded-full px-3 py-1.5 text-sm font-medium shadow-sm hover:bg-[var(--ai-hover-surface)]"
            style={{ background: tokens.surfaceElevated, color: tokens.accentSecondary }}
          >
            {t('开启新学习会话', 'Start new chat')}
          </button>
        )}
      </div>
    );
  };

  const renderComposer = () => (
    <TutorComposer
      input={chat.input}
      isSending={chat.isSending || chat.isProfilesLoading}
      language={language}
      quickActions={quickActions}
      conversationNotice={renderConversationNotice()}
      t={t}
      onInputChange={chat.setInput}
      onSend={chat.sendMessage}
      tokens={tokens}
    />
  );

  return (
    <div
      className="bg-[var(--ai-surface-elevated)]"
      style={{
        ...textStyle,
        position: 'fixed',
        inset: 0,
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        color: tokens.textPrimary,
      }}
    >
      <div style={{ width: '100%', height: '100%', minHeight: 0 }}>
        <TutorSidebar
          sidebarOpen={sidebarOpen}
          sidebarWidth={sidebarWidth}
          tokens={tokens}
          language={language}
          profiles={chat.profiles}
          selectedProfile={chat.selectedProfile}
          customPrompt={chat.customPrompt}
          materials={materials.materials}
          selectedMaterialIds={materials.selectedMaterialIds}
          isUploadingMaterial={materials.isUploadingMaterial}
          materialError={materials.materialError}
          loadError={loadError}
          historyLoadError={historyLoadError}
          remainingSeconds={remainingSeconds}
          timerState={timerState}
          isRunning={isRunning}
          timerHasStarted={timerHasStarted}
          historySearchOpen={history.historySearchOpen}
          historySearchQuery={history.historySearchQuery}
          isSearchingHistory={history.isSearchingHistory}
          historyItems={history.historyItems}
          activeConversationId={chat.activeConversationId}
          materialInputRef={materialInputRef}
          historySearchInputRef={historySearchInputRef}
          t={t}
          onExit={onExit}
          onCollapse={() => setSidebarOpen(false)}
          onStartNewChat={chat.startNewChat}
          onToggleHistorySearch={history.toggleHistorySearch}
          onCloseHistorySearch={history.closeHistorySearch}
          onHistorySearchQueryChange={history.setHistorySearchQuery}
          onSelectedProfileChange={chat.setSelectedProfile}
          onCustomPromptChange={chat.setCustomPrompt}
          onMaterialUpload={materials.handleMaterialUpload}
          onToggleMaterialSelection={materials.toggleMaterialSelection}
          onToggleTimer={toggleTimer}
          onResetTimer={resetTimer}
          onStartNextRound={startNextRound}
          onOpenHistoryItem={(id) => void history.openHistoryItem(id)}
          onExportHistoryItem={(id) => void history.exportHistoryItem(id)}
          onRemoveHistoryItem={(id) => void history.removeHistoryItem(id)}
        />

        <main
          className="bg-[var(--ai-surface-elevated)]"
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            bottom: 0,
            left: sidebarOpen ? sidebarWidth : 0,
            display: 'flex',
            minHeight: 0,
            flexDirection: 'column',
            overflow: 'hidden',
            transition: 'left 180ms ease',
          }}
        >
          <header className="flex h-14 items-center justify-between px-5" style={{ flexShrink: 0 }}>
            <div>
              {!sidebarOpen && (
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="flex h-9 w-9 items-center justify-center rounded-lg hover:bg-[var(--ai-hover-surface)]"
                  aria-label={t('打开侧边栏', 'Open sidebar')}
                >
                  <PanelLeftOpen className="h-5 w-5" />
                </button>
              )}
            </div>
            <div
              className="flex items-center gap-2 text-sm"
              style={{ color: tokens.textSecondary }}
            >
              <span
                className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
                style={{
                  background: focusToneStyle.background,
                  borderColor: focusToneStyle.borderColor,
                  color: focusToneStyle.color,
                }}
                title={`${modeLabel} | ${detailText}`}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: focusToneStyle.dot }}
                />
                {focusText}
              </span>
              <span
                className="rounded-full px-2 py-1 text-xs"
                style={{
                  background: tokens.surfaceMuted,
                  border: tokens.borderSubtle,
                  color: tokens.textSecondary,
                }}
              >
                {language === 'zh' ? `当前阶段：${phaseText}` : `Phase: ${phaseText}`}
              </span>
              <span
                className="hidden max-w-[420px] truncate text-xs lg:inline"
                style={{ color: tokens.textMuted }}
                title={detailText}
              >
                {detailText}
              </span>
            </div>
          </header>

          <div
            ref={scrollRef}
            className="px-5"
            style={{ minHeight: 0, flex: 1, overflowY: 'auto', overscrollBehavior: 'contain' }}
            onScroll={handleScroll}
          >
            {chat.errorBanner && (
              <div
                className="mx-auto mt-2 flex max-w-3xl items-start gap-2 rounded-2xl border px-4 py-3 text-sm"
                style={statusPanelStyle(tokens, 'warning')}
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">{chat.errorBanner}</div>
                <button
                  onClick={chat.dismissErrorBanner}
                  className="rounded-md px-2 py-0.5 text-xs font-medium hover:bg-[var(--ai-hover-surface)]"
                >
                  {t('关闭', 'Dismiss')}
                </button>
                {chat.retryLastMessage && (
                  <button
                    onClick={() => void chat.retryLastMessage?.()}
                    className="rounded-md px-2 py-0.5 text-xs font-medium hover:bg-[var(--ai-hover-surface)]"
                  >
                    {t('重试', 'Retry')}
                  </button>
                )}
                {chat.errorCode === 'llm_provider_not_configured' && onConfigureModel && (
                  <button
                    onClick={onConfigureModel}
                    className="rounded-md px-2 py-0.5 text-xs font-medium hover:bg-[var(--ai-hover-surface)]"
                  >
                    {t('配置模型', 'Configure model')}
                  </button>
                )}
              </div>
            )}
            {chat.messages.length === 0 ? (
              <div
                className="flex flex-col items-center justify-center text-center"
                style={{ minHeight: '66vh', maxWidth: 900, margin: '0 auto', paddingTop: 18 }}
              >
                <h1
                  className="leading-tight tracking-normal"
                  style={{
                    fontSize: 40,
                    fontFamily:
                      language === 'zh'
                        ? '"STXingkai", "KaiTi", "Kaiti SC", "KaiTi TC", "SimKai", serif'
                        : '"Georgia", "Times New Roman", serif',
                    fontWeight: 400,
                    letterSpacing: 0,
                    color: tokens.textPrimary,
                  }}
                >
                  {t('准备好了，随时开始', 'Ready when you are')}
                </h1>
                <div style={{ width: '100%', marginTop: 48 }}>{renderComposer()}</div>
              </div>
            ) : (
              <TutorMessageList
                messages={chat.messages}
                materialContext={chat.activeMaterialContext}
                isSending={chat.isSending}
                language={language}
                t={t}
                tokens={tokens}
              />
            )}
          </div>

          {chat.messages.length > 0 && (
            <div className="px-5 pb-6 pt-2" style={{ flexShrink: 0 }}>
              {renderComposer()}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
