import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  deleteLlmCredential,
  fetchLlmCredentials,
  patchLlmCredential,
  saveLlmCredential,
} from './llmCredentialsApi';

describe('llmCredentialsApi', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('saves provider credentials with PUT and never stores API keys in browser storage', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          credential: {
            provider_id: 'linkapi',
            configured: true,
            enabled: true,
            is_default: true,
            api_key_fingerprint: 'abc123',
          },
        }),
        { status: 200 },
      ),
    );

    const result = await saveLlmCredential('linkapi', {
      api_key: 'sk-user-secret',
      base_url: 'https://api.linkapi.ai/v1',
      default_model: 'claude-sonnet-4-20250514',
      is_default: true,
      is_enabled: true,
    });

    expect(result.provider_id).toBe('linkapi');
    expect(window.localStorage.getItem('sk-user-secret')).toBeNull();
    const [, options] = fetchSpy.mock.calls[0];
    expect(options?.method).toBe('PUT');
    expect(String(options?.body)).toContain('sk-user-secret');
  });

  it('patches metadata without accepting an api_key field', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ credential: { provider_id: 'openai', configured: true } }), {
        status: 200,
      }),
    );

    await expect(
      patchLlmCredential('openai', {
        default_model: 'gpt-4o-mini',
        // @ts-expect-error api_key must be rejected at runtime too.
        api_key: 'sk-should-not-send',
      }),
    ).rejects.toThrow('API key updates must use saveLlmCredential');
  });

  it('lists and deletes credentials through authenticated apiFetch paths', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ credentials: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ deleted: true }), { status: 200 }));

    await expect(fetchLlmCredentials()).resolves.toEqual([]);
    await expect(deleteLlmCredential('openai')).resolves.toEqual({ deleted: true });
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/api/llm/credentials');
    expect(String(fetchSpy.mock.calls[1][0])).toContain('/api/llm/credentials/openai');
    expect(fetchSpy.mock.calls[1][1]?.method).toBe('DELETE');
  });
});
