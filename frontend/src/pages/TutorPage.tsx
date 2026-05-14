import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import { TutorChatWorkspace } from '../components/TutorChatWorkspace';

export function TutorPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const refreshDashboard = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['dashboard-summary', user?.username] });
  }, [queryClient, user?.username]);

  return (
    <TutorChatWorkspace
      trainingMode="focus"
      onExit={() => navigate('/')}
      onConfigureModel={() => navigate('/settings/model')}
      onPomodoroLogged={refreshDashboard}
    />
  );
}
