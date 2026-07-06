import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteTutorConversation,
  exportTutorConversation,
  fetchTutorConversation,
  fetchTutorConversations,
  searchTutorConversations,
  type TutorConversationDetail,
  type TutorConversationSummary,
} from '../../utils/chatApi';
import { getUserFacingError } from '../../utils/apiClient';
import { useDebouncedValue } from '../../utils/useDebouncedValue';
import { tutorQueryKeys } from './tutorQueryKeys';

interface UseTutorHistoryOptions {
  activeConversationId: number | null;
  onConversationOpened: (conversation: TutorConversationDetail) => void;
  onActiveConversationRemoved: () => void;
}

export function useTutorHistory({
  activeConversationId,
  onConversationOpened,
  onActiveConversationRemoved,
}: UseTutorHistoryOptions) {
  const queryClient = useQueryClient();
  const [historySearchOpen, setHistorySearchOpen] = useState(false);
  const [historySearchQuery, setHistorySearchQuery] = useState('');
  const [loadErrorState, setLoadErrorState] = useState<string | null>(null);
  const debouncedHistorySearchQuery = useDebouncedValue(historySearchQuery.trim(), 250);
  const effectiveHistorySearchQuery = historySearchOpen ? debouncedHistorySearchQuery : '';

  const conversationsQuery = useQuery({
    queryKey: tutorQueryKeys.conversations(effectiveHistorySearchQuery),
    queryFn: ({ signal }) =>
      effectiveHistorySearchQuery
        ? searchTutorConversations(effectiveHistorySearchQuery, { signal })
        : fetchTutorConversations({ signal }),
    placeholderData: (previousData) => previousData,
    retry: false,
  });

  const historyItems = useMemo(() => conversationsQuery.data ?? [], [conversationsQuery.data]);
  const queryLoadError = useMemo(
    () => (conversationsQuery.error ? getUserFacingError(conversationsQuery.error) : null),
    [conversationsQuery.error],
  );

  const openHistoryItem = async (id: number) => {
    setLoadErrorState(null);

    try {
      const conversation = await queryClient.fetchQuery({
        queryKey: tutorQueryKeys.conversation(id),
        queryFn: ({ signal }) => fetchTutorConversation(id, { signal }),
      });
      onConversationOpened(conversation);
    } catch (error) {
      setLoadErrorState(getUserFacingError(error));
    }
  };

  const removeHistoryItem = async (id: number) => {
    setLoadErrorState(null);

    try {
      await deleteTutorConversation(id);
      queryClient.removeQueries({ queryKey: tutorQueryKeys.conversation(id) });
      queryClient.setQueriesData<TutorConversationSummary[]>(
        { queryKey: ['tutor', 'conversations'] },
        (items) => items?.filter((item) => item.id !== id) ?? [],
      );

      if (activeConversationId === id) {
        onActiveConversationRemoved();
      }
    } catch (error) {
      setLoadErrorState(getUserFacingError(error));
    }
  };

  const exportHistoryItem = async (id: number) => {
    setLoadErrorState(null);

    try {
      const exported = await exportTutorConversation(id);
      const blob = new Blob([exported.content], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = exported.filename || `tutor-conversation-${id}.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setLoadErrorState(getUserFacingError(error));
    }
  };

  const closeHistorySearch = () => {
    setHistorySearchOpen(false);
    setHistorySearchQuery('');
  };

  const toggleHistorySearch = () => {
    if (historySearchOpen) {
      closeHistorySearch();
      return;
    }

    setHistorySearchOpen(true);
  };

  return {
    historySearchOpen,
    historySearchQuery,
    historyItems,
    isSearchingHistory: historySearchOpen && conversationsQuery.isFetching,
    isLoadingHistory: conversationsQuery.isLoading,
    loadError: loadErrorState ?? queryLoadError,
    setHistorySearchQuery,
    closeHistorySearch,
    toggleHistorySearch,
    openHistoryItem,
    removeHistoryItem,
    exportHistoryItem,
  };
}
