import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Brain } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui/button';
import { getUserFacingError } from '../utils/apiClient';
import { cardSurfaceStyle, primaryActionStyle } from '../utils/glassStyles';
import { useSettings } from '../utils/settings';

const USERNAME_PATTERN = /^[a-zA-Z0-9_-]{3,64}$/;

export function RegisterPage() {
  const { user, register, login } = useAuth();
  const { tokens, textStyle, t } = useSettings();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    const cleanUsername = username.trim();
    if (!USERNAME_PATTERN.test(cleanUsername)) {
      setError(t('用户名只能包含字母、数字、下划线或短横线，长度 3-64。', 'Username must be 3-64 letters, numbers, underscores, or hyphens.'));
      return;
    }
    if (password.length < 8 || password.length > 128) {
      setError(t('密码长度需要在 8 到 128 位之间。', 'Password must be 8-128 characters.'));
      return;
    }
    if (password !== confirmPassword) {
      setError(t('两次输入的密码不一致。', 'Passwords do not match.'));
      return;
    }

    setIsSubmitting(true);
    try {
      await register({ username: cleanUsername, password, email: email.trim() || undefined });
      await login(cleanUsername, password);
      navigate('/', { replace: true });
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
              {t('创建独立学习账号', 'Create your study account')}
            </p>
          </div>
        </div>

        <input className="mb-3 w-full rounded-xl border px-4 py-3 outline-none" style={{ background: tokens.surface, borderColor: tokens.borderStrong, color: tokens.textPrimary }} placeholder={t('用户名', 'Username')} value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
        <input className="mb-3 w-full rounded-xl border px-4 py-3 outline-none" style={{ background: tokens.surface, borderColor: tokens.borderStrong, color: tokens.textPrimary }} placeholder={t('邮箱（可选）', 'Email (optional)')} value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
        <input className="mb-3 w-full rounded-xl border px-4 py-3 outline-none" style={{ background: tokens.surface, borderColor: tokens.borderStrong, color: tokens.textPrimary }} placeholder={t('密码', 'Password')} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required />
        <input className="mb-4 w-full rounded-xl border px-4 py-3 outline-none" style={{ background: tokens.surface, borderColor: tokens.borderStrong, color: tokens.textPrimary }} placeholder={t('重复密码', 'Confirm password')} type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" required />

        {error ? <p className="mb-4 text-sm text-red-500">{error}</p> : null}

        <Button type="submit" disabled={isSubmitting} className="w-full rounded-xl py-3 text-white" style={primaryActionStyle(tokens)}>
          {isSubmitting ? t('注册中...', 'Creating...') : t('注册并登录', 'Create account')}
        </Button>

        <p className="mt-5 text-center text-sm" style={{ color: tokens.textSecondary }}>
          {t('已有账号？', 'Already have an account?')}{' '}
          <Link to="/login" className="font-semibold" style={{ color: tokens.textPrimary }}>
            {t('登录', 'Sign in')}
          </Link>
        </p>
      </form>
    </main>
  );
}
