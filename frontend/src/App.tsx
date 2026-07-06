import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { PageSkeleton } from './components/PageSkeleton';

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((module) => ({ default: module.DashboardPage })),
);
const LoginPage = lazy(() =>
  import('./pages/LoginPage').then((module) => ({ default: module.LoginPage })),
);
const RegisterPage = lazy(() =>
  import('./pages/RegisterPage').then((module) => ({ default: module.RegisterPage })),
);
const SettingsModelPage = lazy(() =>
  import('./pages/SettingsModelPage').then((module) => ({ default: module.SettingsModelPage })),
);
const TutorPage = lazy(() =>
  import('./pages/TutorPage').then((module) => ({ default: module.TutorPage })),
);

export default function App() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/tutor" element={<TutorPage />} />
          <Route path="/settings/model" element={<SettingsModelPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
