import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  FALLBACK_PROMPT_PROFILES,
  fetchPromptProfiles,
  sendTutorChat,
  type LearningPhase,
  type MaterialContext,
  type TutorChatRequest,
  type TutorConversationDetail,
  type TutorConversationSummary,
} from '../../utils/chatApi';
import { ApiError, getUserFacingError, isAbortError } from '../../utils/apiClient';
import type { Language } from '../../utils/settings';
import { tutorQueryKeys } from './tutorQueryKeys';
import type { ChatMessage, ChatRole, TimerState } from '../../components/tutor/types';

interface UseTutorChatOptions {
  language: Language;
  t: <T extends string>(zh: T, en: T) => T;
  trainingMode: string;
  timerState: TimerState;
  remainingSeconds: number;
  selectedMaterialIds: number[];
}

interface FailedSendRequest {
  request: TutorChatRequest;
  nextMessages: ChatMessage[];
  profileId: string;
}

interface TutorChatState {
  selectedProfile: string;
  learningPhase: LearningPhase;
  customPrompt: string;
  messages: ChatMessage[];
  activeMaterialContext: MaterialContext | null;
  activeConversationId: number | null;
  currentExchangeCount: number;
  currentSummary: string | null;
  carryOverSummary: string | null;
  carryOverMessages: ChatMessage[];
  input: string;
  isSending: boolean;
  errorBanner: string | null;
  errorCode: string | null;
  lastFailedRequest: FailedSendRequest | null;
}

type TutorChatAction =
  | { type: 'patch'; updates: Partial<TutorChatState> }
  | { type: 'start-new-chat'; carryOverSummary: string | null; carryOverMessages: ChatMessage[] }
  | { type: 'apply-conversation'; conversation: TutorConversationDetail }
  | { type: 'append-timer-message'; content: string };

const initialState: TutorChatState = {
  selectedProfile: 'three_stage',
  learningPhase: 'general',
  customPrompt: '',
  messages: [],
  activeMaterialContext: null,
  activeConversationId: null,
  currentExchangeCount: 0,
  currentSummary: null,
  carryOverSummary: null,
  carryOverMessages: [],
  input: '',
  isSending: false,
  errorBanner: null,
  errorCode: null,
  lastFailedRequest: null,
};

function tutorChatReducer(state: TutorChatState, action: TutorChatAction): TutorChatState {
  switch (action.type) {
    case 'patch':
      return { ...state, ...action.updates };
    case 'start-new-chat':
      return {
        ...state,
        messages: [],
        activeConversationId: null,
        currentExchangeCount: 0,
        currentSummary: null,
        carryOverSummary: action.carryOverSummary,
        carryOverMessages: action.carryOverMessages,
        activeMaterialContext: null,
        learningPhase: 'general',
        input: '',
        isSending: false,
        errorBanner: null,
        errorCode: null,
        lastFailedRequest: null,
      };
    case 'apply-conversation':
      return {
        ...state,
        activeConversationId: action.conversation.id,
        currentExchangeCount: action.conversation.exchange_count ?? Math.floor(action.conversation.message_count / 2),
        currentSummary: action.conversation.summary || null,
        carryOverSummary: null,
        carryOverMessages: [],
        activeMaterialContext: null,
        learningPhase: 'general',
        messages: toChatMessages(action.conversation.messages),
        input: '',
        isSending: false,
        errorBanner: null,
        errorCode: null,
        lastFailedRequest: null,
      };
    case 'append-timer-message':
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: createMessageId(),
            role: 'assistant',
            label: 'Timer',
            content: action.content,
          },
        ],
      };
    default:
      return state;
  }
}

function createMessageId() {
  const browserCrypto = globalThis.crypto;

  if (browserCrypto?.randomUUID) {
    return browserCrypto.randomUUID();
  }

  if (browserCrypto?.getRandomValues) {
    const bytes = new Uint8Array(16);
    browserCrypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  }

  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function normalizeLearningPhase(phase?: string | null): LearningPhase {
  if (phase === 'planning' || phase === 'understanding' || phase === 'feynman' || phase === 'general') {
    return phase;
  }
  return 'general';
}

function toChatMessages(
  messages: { id?: string | number; role: string; content: string; label?: string | null }[],
  credentialSource?: 'user' | 'global' | 'local',
  credentialFingerprint?: string | null,
): ChatMessage[] {
  const visibleMessages = messages.filter((message) => message.role === 'user' || message.role === 'assistant');
  const lastAssistantIndex = visibleMessages.reduce(
    (lastIndex, message, index) => (message.role === 'assistant' ? index : lastIndex),
    -1,
  );
  return visibleMessages.map((message, index) => ({
      id: String(message.id ?? createMessageId()),
      role: message.role as ChatRole,
      content: message.content,
      label: message.label || undefined,
      credentialSource: message.role === 'assistant' && index === lastAssistantIndex ? credentialSource : undefined,
      credentialFingerprint: message.role === 'assistant' && index === lastAssistantIndex ? credentialFingerprint : undefined,
    }));
}

export function useTutorChat({
  language,
  t,
  trainingMode,
  timerState,
  remainingSeconds,
  selectedMaterialIds,
}: UseTutorChatOptions) {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(tutorChatReducer, initialState);
  const activeAbortControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const profilesQuery = useQuery({
    queryKey: tutorQueryKeys.profiles(),
    queryFn: ({ signal }) => fetchPromptProfiles({ signal }),
    retry: false,
  });

  const profiles = useMemo(
    () => (profilesQuery.data && profilesQuery.data.length > 0 ? profilesQuery.data : FALLBACK_PROMPT_PROFILES),
    [profilesQuery.data],
  );
  const currentProfile = useMemo(
    () => profiles.find((profile) => profile.id === state.selectedProfile),
    [profiles, state.selectedProfile],
  );
  const visibleExchangeCount = Math.max(
    state.currentExchangeCount,
    state.messages.filter((message) => message.role === 'user').length,
  );
  const loadError = useMemo(
    () => (profilesQuery.error ? t('学习策略暂时使用本地默认配置', 'Using local default learning strategies') : null),
    [profilesQuery.error, t],
  );
  const modeLabel = useMemo(() => {
    if (trainingMode === 'light') return language === 'zh' ? '轻度学习' : 'Light study';
    if (trainingMode === 'break') return language === 'zh' ? '休息恢复' : 'Rest reset';
    return language === 'zh' ? '深度专注' : 'Deep focus';
  }, [language, trainingMode]);

  useEffect(() => {
    if (!profiles.length) return;
    if (!profiles.some((profile) => profile.id === state.selectedProfile)) {
      dispatch({ type: 'patch', updates: { selectedProfile: profiles[0].id } });
    }
  }, [profiles, state.selectedProfile]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      activeAbortControllerRef.current?.abort();
    };
  }, []);

  const abortActiveRequest = useCallback(() => {
    activeAbortControllerRef.current?.abort();
    activeAbortControllerRef.current = null;
  }, []);

  const startNewChat = useCallback(() => {
    const shouldCarryContext = state.currentExchangeCount >= 15 && Boolean(state.currentSummary);
    const carryOverSummary = shouldCarryContext ? state.currentSummary : null;
    const carryOverMessages = shouldCarryContext
      ? state.messages
          .filter((message) => message.role === 'user' || (message.role === 'assistant' && message.label !== 'Timer'))
          .slice(-12)
      : [];

    abortActiveRequest();
    dispatch({
      type: 'start-new-chat',
      carryOverSummary,
      carryOverMessages,
    });
  }, [abortActiveRequest, state.currentExchangeCount, state.currentSummary, state.messages]);

  const applyConversation = useCallback(
    (conversation: TutorConversationDetail) => {
      abortActiveRequest();
      dispatch({ type: 'apply-conversation', conversation });
    },
    [abortActiveRequest],
  );

  const appendTimerMessage = useCallback((content: string) => {
    dispatch({ type: 'append-timer-message', content });
  }, []);

  const dismissErrorBanner = useCallback(() => {
    dispatch({ type: 'patch', updates: { errorBanner: null, errorCode: null } });
  }, []);

  const executeSend = useCallback(
    async (request: TutorChatRequest, nextMessages: ChatMessage[], profileId: string) => {
      const controller = new AbortController();
      activeAbortControllerRef.current = controller;

      dispatch({
        type: 'patch',
        updates: {
          isSending: true,
          errorBanner: null,
          errorCode: null,
          activeMaterialContext: null,
        },
      });

      try {
        const response = await sendTutorChat(request, { signal: controller.signal });
        const profileLabel =
          profiles.find((profile) => profile.id === response.prompt_profile)?.name ??
          profiles.find((profile) => profile.id === profileId)?.name ??
          currentProfile?.name ??
          'Tutor';

        if (response.messages?.length) {
          dispatch({
            type: 'patch',
            updates: {
              messages: toChatMessages(response.messages, response.credential_source, response.credential_fingerprint),
            },
          });
        } else {
          dispatch({
            type: 'patch',
            updates: {
              messages: [
                ...nextMessages,
                {
                  id: createMessageId(),
                  role: 'assistant',
                  label: profileLabel,
                  content: response.message.content,
                  credentialSource: response.credential_source,
                  credentialFingerprint: response.credential_fingerprint,
                },
              ],
            },
          });
        }

        if (response.conversation_id) {
          dispatch({ type: 'patch', updates: { activeConversationId: response.conversation_id } });
        }

        dispatch({
          type: 'patch',
          updates: {
            learningPhase: normalizeLearningPhase(response.learning_phase),
            currentExchangeCount:
              response.exchange_count ??
              response.conversation?.exchange_count ??
              nextMessages.filter((message) => message.role === 'user').length,
            currentSummary: response.conversation?.summary ?? state.currentSummary,
            activeMaterialContext: response.material_context ?? null,
            errorCode: null,
            lastFailedRequest: null,
          },
        });

        if (response.conversation) {
          queryClient.setQueriesData<TutorConversationSummary[]>({ queryKey: ['tutor', 'conversations'] }, (items) => {
            const conversations = items ?? [];
            return [
              response.conversation as TutorConversationSummary,
              ...conversations.filter((item) => item.id !== response.conversation?.id),
            ];
          });
          queryClient.setQueryData(tutorQueryKeys.conversation(response.conversation.id), response.conversation);
        }

        void queryClient.invalidateQueries({ queryKey: ['tutor', 'conversations'] });
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }

        const message = getUserFacingError(error);
        dispatch({
          type: 'patch',
          updates: {
            errorBanner: message,
            errorCode: error instanceof ApiError ? error.code : null,
            lastFailedRequest: { request, nextMessages, profileId },
          },
        });
      } finally {
        if (activeAbortControllerRef.current === controller) {
          activeAbortControllerRef.current = null;
        }
        if (mountedRef.current) {
          dispatch({ type: 'patch', updates: { isSending: false } });
        }
      }
    },
    [currentProfile?.name, profiles, queryClient, state.currentSummary],
  );

  const sendMessage = useCallback(
    async (content: string, nextProfile = state.selectedProfile) => {
      const trimmed = content.trim();
      if (!trimmed || state.isSending) return;

      const resolvedProfile = profiles.find((profile) => profile.id === nextProfile) ?? profiles[0];
      if (!resolvedProfile) return;

      const userMessage: ChatMessage = {
        id: createMessageId(),
        role: 'user',
        content: trimmed,
      };
      const nextMessages = [...state.messages, userMessage];
      const request: TutorChatRequest = {
        conversation_id: state.activeConversationId,
        provider: 'auto',
        prompt_profile: resolvedProfile.id,
        system_prompt_override: resolvedProfile.id === 'custom' ? state.customPrompt : null,
        messages: nextMessages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
        tutor_context: {
          mode: trainingMode,
          mode_label: modeLabel,
          timer_state: timerState,
          remaining_seconds: remainingSeconds,
          learning_phase: state.learningPhase,
          goal: 'AI Tutor learning session',
          previous_session_summary: state.carryOverSummary,
          recent_context_messages: state.carryOverMessages.map((message) => ({
            role: message.role,
            content: message.content,
          })),
          material_ids: selectedMaterialIds,
        },
      };

      dispatch({
        type: 'patch',
        updates: {
          messages: nextMessages,
          input: '',
          selectedProfile: resolvedProfile.id,
          isSending: true,
          errorBanner: null,
          errorCode: null,
          activeMaterialContext: null,
          lastFailedRequest: null,
        },
      });

      await executeSend(request, nextMessages, resolvedProfile.id);
    },
    [
      executeSend,
      modeLabel,
      profiles,
      remainingSeconds,
      selectedMaterialIds,
      state.activeConversationId,
      state.carryOverMessages,
      state.carryOverSummary,
      state.customPrompt,
      state.isSending,
      state.learningPhase,
      state.messages,
      state.selectedProfile,
      timerState,
      trainingMode,
    ],
  );

  const retryLastMessage = useCallback(async () => {
    const failedRequest = state.lastFailedRequest;
    if (!failedRequest || state.isSending) return;

    await executeSend(failedRequest.request, failedRequest.nextMessages, failedRequest.profileId);
  }, [executeSend, state.isSending, state.lastFailedRequest]);

  const setSelectedProfile = useCallback((selectedProfile: string) => {
    dispatch({ type: 'patch', updates: { selectedProfile } });
  }, []);

  const setCustomPrompt = useCallback((customPrompt: string) => {
    dispatch({ type: 'patch', updates: { customPrompt } });
  }, []);

  const setInput = useCallback((input: string) => {
    dispatch({ type: 'patch', updates: { input } });
  }, []);

  const setLearningPhase = useCallback((learningPhase: LearningPhase) => {
    dispatch({ type: 'patch', updates: { learningPhase } });
  }, []);

  return {
    profiles,
    selectedProfile: state.selectedProfile,
    customPrompt: state.customPrompt,
    messages: state.messages,
    input: state.input,
    isSending: state.isSending,
    errorBanner: state.errorBanner,
    errorCode: state.errorCode,
    activeMaterialContext: state.activeMaterialContext,
    activeConversationId: state.activeConversationId,
    learningPhase: state.learningPhase,
    visibleExchangeCount,
    loadError,
    isProfilesLoading: profilesQuery.isLoading,
    retryLastMessage: state.lastFailedRequest ? retryLastMessage : undefined,
    setSelectedProfile,
    setCustomPrompt,
    setInput,
    setLearningPhase,
    startNewChat,
    applyConversation,
    appendTimerMessage,
    dismissErrorBanner,
    sendMessage,
  };
}
