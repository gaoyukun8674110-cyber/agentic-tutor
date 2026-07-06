import { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../utils/apiClient';
import { useTutorChat } from './useTutorChat';

const { sendTutorChatMock } = vi.hoisted(() => ({
  sendTutorChatMock: vi.fn(),
}));

vi.mock('../../utils/chatApi', async () => {
  const actual = await vi.importActual<typeof import('../../utils/chatApi')>('../../utils/chatApi');

  return {
    ...actual,
    fetchPromptProfiles: vi.fn().mockResolvedValue([]),
    sendTutorChat: sendTutorChatMock,
  };
});

function createWrapper({ strict = false } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    const content = <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    return strict ? <StrictMode>{content}</StrictMode> : content;
  };
}

describe('useTutorChat error localization', () => {
  afterEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('uses the backend user_message directly instead of prefixing an English unavailable label', async () => {
    window.localStorage.setItem('ai-tutor-language', 'zh');
    sendTutorChatMock.mockRejectedValue(
      new ApiError('模型服务暂时不可用', 502, 'llm_provider_error', 'trace-1'),
    );

    const { result } = renderHook(
      () =>
        useTutorChat({
          language: 'zh',
          t: (zh) => zh,
          trainingMode: 'deep',
          timerState: 'focus',
          remainingSeconds: 60,
          selectedMaterialIds: [],
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.sendMessage('测试一下');
    });

    await waitFor(() => {
      expect(result.current.errorBanner).toBe('模型服务暂时不可用 (trace trace-1)');
    });
  });

  it('restores isSending after a StrictMode effect remount', async () => {
    sendTutorChatMock.mockResolvedValue({
      message: { role: 'assistant', content: 'Keep going.' },
      provider: 'e2e',
      model: 'mock',
      prompt_profile: 'three_stage',
      learning_phase: 'general',
      credential_source: 'local',
      credential_fingerprint: null,
    });

    const { result } = renderHook(
      () =>
        useTutorChat({
          language: 'en',
          t: (_zh, en) => en,
          trainingMode: 'deep',
          timerState: 'focus',
          remainingSeconds: 60,
          selectedMaterialIds: [],
        }),
      { wrapper: createWrapper({ strict: true }) },
    );

    await act(async () => {
      await result.current.sendMessage('hello');
    });

    await waitFor(() => {
      expect(result.current.isSending).toBe(false);
    });
  });
});
