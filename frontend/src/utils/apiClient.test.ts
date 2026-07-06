import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiFetch, getUserFacingError, setAccessToken } from './apiClient';

describe('apiClient localization and auth refresh', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setAccessToken(null);
    window.localStorage.clear();
  });

  it('returns Chinese auth errors when the stored language is zh', () => {
    window.localStorage.setItem('ai-tutor-language', 'zh');

    expect(getUserFacingError(new ApiError('Missing access token', 401, 'unauthorized'))).toBe(
      '需要身份验证。请先登录。',
    );
    expect(getUserFacingError(new ApiError('User not allowed', 403, 'forbidden'))).toBe(
      '你没有权限执行此操作。',
    );
  });

  it('sends the current UI language to the backend via Accept-Language', async () => {
    window.localStorage.setItem('ai-tutor-language', 'zh');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await apiFetch<{ ok: boolean }>('/test');

    const [, options] = fetchSpy.mock.calls[0];
    const headers = options?.headers as Headers;
    expect(headers.get('Accept-Language')).toBe('zh-CN');
    expect(options?.credentials).toBe('include');
  });

  it('refreshes once and replays a protected request after 401', async () => {
    setAccessToken('expired-token');
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: { code: 'token_expired', user_message: 'Access token expired' },
          }),
          { status: 401 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'fresh-token' }), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const result = await apiFetch<{ ok: boolean }>('/api/dashboard/summary');

    expect(result.ok).toBe(true);
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    expect(String(fetchSpy.mock.calls[1][0])).toContain('/api/auth/refresh');
    expect((fetchSpy.mock.calls[2][1]?.headers as Headers).get('Authorization')).toBe(
      'Bearer fresh-token',
    );
  });

  it('uses one refresh request for concurrent 401 responses', async () => {
    setAccessToken('expired-token');
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: { code: 'token_expired', user_message: 'Access token expired' },
          }),
          { status: 401 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: { code: 'token_expired', user_message: 'Access token expired' },
          }),
          { status: 401 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'fresh-token' }), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const results = await Promise.all([
      apiFetch<{ ok: boolean }>('/api/dashboard/summary'),
      apiFetch<{ ok: boolean }>('/api/llm/providers'),
    ]);

    expect(results.every((result) => result.ok)).toBe(true);
    expect(
      fetchSpy.mock.calls.filter((call) => String(call[0]).includes('/api/auth/refresh')),
    ).toHaveLength(1);
  });

  it('dispatches logout and throws unauthenticated when refresh does not return a token', async () => {
    setAccessToken('expired-token');
    const logoutListener = vi.fn();
    window.addEventListener('auth:logout', logoutListener);
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: { code: 'token_expired', user_message: 'Access token expired' },
          }),
          { status: 401 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'bad refresh' }), { status: 500 }),
      );

    await expect(apiFetch<{ ok: boolean }>('/api/dashboard/summary')).rejects.toMatchObject({
      code: 'unauthenticated',
      status: 401,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(logoutListener).toHaveBeenCalledTimes(1);
    window.removeEventListener('auth:logout', logoutListener);
  });
});
