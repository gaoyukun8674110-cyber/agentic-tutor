import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Brain } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui/button';
import { getUserFacingError } from '../utils/apiClient';
import { cardSurfaceStyle, primaryActionStyle } from '../utils/glassStyles';
import { useSettings } from '../utils/settings';

export function LoginPage() {
  const { user, login } = useAuth();
  const { tokens, textStyle, t } = useSettings();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('test-01');
  const [password, setPassword] = useState('123456');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/';

  if (user) return <Navigate to={from} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(getUserFacingError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="relative flex min-h-screen items-center justify-center px-6 py-10" style={{ ...textStyle, color: tokens.textPrimary }}>
      <div className="fixed inset-0" style={{ background: tokens.pageGradient }} />
      <form onSubmit={submit} className="relative w-full max-w-md rounded-2xl p-8 shadow-xl" style={cardSurfaceStyle(tokens)}>
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: tokens.surfaceAccent }}>
            <Brain className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">AI Tutor</h1>
            <p className="text-sm" style={{ color: tokens.textSecondary }}>
              {t('登录你的学习空间', 'Sign in to your study workspace')}
            </p>
          </div>
        </div>

        <label className="mb-4 block">
          <span className="mb-2 block text-sm" style={{ color: tokens.textSecondary }}>
            {t('用户名', 'Username')}
          </span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="w-full rounded-xl border px-4 py-3 outline-none"
            style={{ background: tokens.surface, borderColor: tokens.borderStrong, color: tokens.textPrimary }}
            autoComplete="username"
            required
          />
        </label>

        <label className="mb-4 block">
          <span className="mb-2 block text-sm" style={{ color: tokens.textSecondary }}>
            {t('密码', 'Password')}
          </span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-xl border px-4 py-3 outline-none"
            style={{ background: tokens.surface, borderColor: tokens.borderStrong, color: tokens.textPrimary }}
            autoComplete="current-password"
            required
          />
        </label>

        {error ? <p className="mb-4 text-sm text-red-500">{error}</p> : null}

        <Button type="submit" disabled={isSubmitting} className="w-full rounded-xl py-3 text-white" style={primaryActionStyle(tokens)}>
          {isSubmitting ? t('登录中...', 'Signing in...') : t('登录', 'Sign in')}
        </Button>

        <p className="mt-5 text-center text-sm" style={{ color: tokens.textSecondary }}>
          {t('还没有账号？', 'No account yet?')}{' '}
          <Link to="/register" className="font-semibold" style={{ color: tokens.textPrimary }}>
            {t('注册', 'Create one')}
          </Link>
        </p>
      </form>
    </main>
  );
}
