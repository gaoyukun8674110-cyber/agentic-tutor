import { Brain, KeyRound, Languages, LogOut, Moon, Sun } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useSettings } from '../utils/settings';

export function TopNavbar() {
  const { user, logout } = useAuth();
  const { language, toggleLanguage, theme, toggleTheme, tokens, t } = useSettings();
  const navigate = useNavigate();

  const navStyle = {
    background: tokens.surfaceMuted,
    backdropFilter: 'blur(15px)',
    borderBottom: tokens.borderSoft,
    boxShadow: tokens.shadow,
  };

  const chipStyle = {
    background: tokens.surfaceAccent,
    border: tokens.borderSoft,
    color: tokens.textPrimary,
  };

  return (
    <header className="sticky top-0 z-50 w-full px-0 shadow-lg" style={navStyle}>
      <div className="mx-auto max-w-7xl px-6">
        <div className="flex h-16 items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl shadow-md" style={chipStyle}>
              <Brain className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold" style={{ color: tokens.textPrimary }}>
                AI Tutor
              </h1>
              <p className="text-xs" style={{ color: tokens.textSecondary }}>
                {t('学习工作台', 'Study workspace')}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={toggleLanguage}
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition-colors"
              style={chipStyle}
              aria-label="toggle language"
            >
              <Languages className="h-4 w-4" />
              {language === 'zh' ? 'ZH -> EN' : 'EN -> ZH'}
            </button>

            <button
              onClick={toggleTheme}
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition-colors"
              style={chipStyle}
              aria-label="toggle theme"
            >
              {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
              {theme === 'light' ? t('夜间模式', 'Night mode') : t('日间模式', 'Day mode')}
            </button>

            <div className="hidden items-center gap-3 rounded-full px-3 py-1.5 sm:flex" style={chipStyle}>
              <div
                className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold"
                style={{ background: tokens.surface, color: tokens.textPrimary }}
              >
                {(user?.username ?? 'S').slice(0, 1).toUpperCase()}
              </div>
              <div className="text-right">
                <p className="text-sm font-medium" style={{ color: tokens.textPrimary }}>
                  {user?.username ?? t('学习者', 'Student')}
                </p>
                <p className="text-xs" style={{ color: tokens.textSecondary }}>
                  {user?.email ?? t('已登录', 'Signed in')}
                </p>
              </div>
            </div>

            <button
              onClick={() => navigate('/settings/model')}
              className="flex h-10 w-10 items-center justify-center rounded-xl transition-colors"
              style={chipStyle}
              aria-label="model settings"
              title={t('模型配置', 'Model settings')}
            >
              <KeyRound className="h-4 w-4" />
            </button>

            <button
              onClick={() => void logout()}
              className="flex h-10 w-10 items-center justify-center rounded-xl transition-colors"
              style={chipStyle}
              aria-label="logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
