import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LoginPage } from './LoginPage';

const loginMock = vi.fn();

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    login: loginMock,
  }),
}));

vi.mock('../utils/settings', () => ({
  useSettings: () => ({
    tokens: {
      textPrimary: '#111111',
      textSecondary: '#666666',
      textInverted: '#ffffff',
      pageGradient: '#ffffff',
      surface: '#ffffff',
      surfaceAccent: '#eeeeee',
      borderStrong: '#dddddd',
      primaryActionGradient: '#111111',
    },
    textStyle: {},
    t: (_zh: string, en: string) => en,
  }),
}));

vi.mock('../utils/glassStyles', () => ({
  cardSurfaceStyle: () => ({}),
  primaryActionStyle: () => ({}),
}));

function renderLoginPage() {
  window.localStorage.setItem('ai-tutor-language', 'en');
  return render(
    <MemoryRouter
      initialEntries={[{ pathname: '/login', state: { from: { pathname: '/tutor' } } }]}
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/tutor" element={<div>Tutor destination</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LoginPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('submits trimmed credentials and returns to the protected source route', async () => {
    loginMock.mockResolvedValue(undefined);
    renderLoginPage();

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: ' alice ' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password-123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(loginMock).toHaveBeenCalledWith('alice', 'password-123'));
    expect(await screen.findByText('Tutor destination')).toBeInTheDocument();
  });

  it('does not prefill the public demo credentials', () => {
    renderLoginPage();

    expect(screen.getByLabelText('Username')).toHaveValue('');
    expect(screen.getByLabelText('Password')).toHaveValue('');
    expect(screen.getByLabelText('Username')).toHaveAttribute('placeholder', 'Username');
    expect(screen.getByLabelText('Password')).toHaveAttribute('placeholder', 'Password');
  });

  it('shows the backend-facing error and keeps the user on the login form', async () => {
    loginMock.mockRejectedValue(new Error('Invalid credentials'));
    renderLoginPage();

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  });
});
