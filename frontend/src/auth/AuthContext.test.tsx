import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, useAuth } from './AuthContext';
import { getAccessToken, setAccessToken } from '../utils/apiClient';

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  const status = init.status ?? 200;
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

function AuthProbe() {
  const { user, isBootstrapping, logout } = useAuth();
  return (
    <div>
      <div data-testid="bootstrap">{String(isBootstrapping)}</div>
      <div data-testid="user">{user?.username ?? 'none'}</div>
      <button onClick={() => void logout()}>Logout</button>
    </div>
  );
}

describe('AuthProvider', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setAccessToken(null);
  });

  it('refreshes an access token on boot and loads the current user with bearer auth', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/auth/refresh')) {
        return jsonResponse({ access_token: 'access-1' });
      }
      if (url.endsWith('/api/auth/me')) {
        expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer access-1');
        return jsonResponse({
          user: {
            id: 1,
            username: 'alice',
            email: null,
            created_at: '2026-05-15T00:00:00+00:00',
          },
        });
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId('bootstrap')).toHaveTextContent('true');
    expect(await screen.findByTestId('user')).toHaveTextContent('alice');
    expect(screen.getByTestId('bootstrap')).toHaveTextContent('false');
    expect(getAccessToken()).toBe('access-1');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('clears the token and user when logging out', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/api/auth/refresh')) {
        return jsonResponse({ access_token: 'access-1' });
      }
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse({
          user: {
            id: 1,
            username: 'alice',
            email: null,
            created_at: '2026-05-15T00:00:00+00:00',
          },
        });
      }
      if (url.endsWith('/api/auth/logout')) {
        return jsonResponse({}, { status: 204 });
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    expect(await screen.findByTestId('user')).toHaveTextContent('alice');
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));

    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('none'));
    expect(getAccessToken()).toBeNull();
  });
});
