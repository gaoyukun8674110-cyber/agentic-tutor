import { BookOpen, Loader2 } from 'lucide-react';

import type { MaterialContext } from '../../utils/chatApi';
import { chatBubbleStyle } from '../../utils/glassStyles';
import type { Language, ThemeTokens } from '../../utils/settings';
import { MathMessage } from '../MathMessage';
import type { ChatMessage } from './types';

interface TutorMessageListProps {
  messages: ChatMessage[];
  materialContext: MaterialContext | null;
  isSending: boolean;
  language: Language;
  tokens: ThemeTokens;
  t: <T extends string>(zh: T, en: T) => T;
}

export function TutorMessageList({
  messages,
  materialContext,
  isSending,
  language,
  tokens,
  t,
}: TutorMessageListProps) {
  const chunks = materialContext?.chunks ?? [];
  const credentialLabel = (message: ChatMessage) => {
    if (message.credentialSource === 'user') return t('你的 Key', 'Your key');
    if (message.credentialSource === 'global') return t('Demo Key', 'Demo key');
    if (message.credentialSource === 'local') return t('本地 Ollama', 'Local Ollama');
    return null;
  };

  return (
    <div className="space-y-6 py-8" style={{ maxWidth: 820, margin: '0 auto' }}>
      {messages.map((message) => {
        const isUser = message.role === 'user';
        return (
          <div
            key={message.id}
            className="flex w-full"
            style={{ justifyContent: isUser ? 'flex-end' : 'flex-start' }}
          >
            <div
              className="rounded-3xl px-5 py-4 text-base leading-7"
              style={{
                ...chatBubbleStyle(tokens, isUser),
                maxWidth: isUser ? '68%' : '82%',
                marginLeft: isUser ? 'auto' : 0,
                marginRight: isUser ? 0 : 'auto',
              }}
            >
              {(message.label || message.credentialSource) && !isUser && (
                <div
                  className="mb-2 flex flex-wrap items-center gap-2 text-xs font-medium"
                  style={{ color: tokens.textSecondary }}
                >
                  {message.label && <span>{message.label}</span>}
                  {credentialLabel(message) && (
                    <span
                      className="rounded-full border px-2 py-0.5"
                      style={{
                        borderColor: 'var(--ai-border-subtle)',
                        background: tokens.surfaceMuted,
                      }}
                    >
                      {credentialLabel(message)}
                    </span>
                  )}
                </div>
              )}
              <MathMessage content={message.content} isUser={isUser} />
            </div>
          </div>
        );
      })}

      {chunks.length > 0 && (
        <div
          className="rounded-2xl px-4 py-3 text-sm"
          style={{
            background: tokens.sourceSurface,
            border: tokens.sourceBorder,
            color: tokens.sourceText,
          }}
        >
          <div
            className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-normal"
            style={{ color: tokens.accentPrimary }}
          >
            <BookOpen className="h-4 w-4" />
            {t('引用资料', 'Retrieved sources')}
          </div>
          <div className="space-y-2">
            {chunks.slice(0, 3).map((chunk, index) => (
              <div key={`${chunk.material_id}-${chunk.chunk_id ?? index}`} className="min-w-0">
                <div
                  className="truncate text-xs font-medium"
                  style={{ color: tokens.accentPrimary }}
                >
                  {chunk.source_label}
                </div>
                <div
                  className="line-clamp-2 text-xs leading-5"
                  style={{ color: tokens.textSecondary }}
                >
                  {chunk.content}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isSending && (
        <div className="flex items-center gap-2 text-sm" style={{ color: tokens.textSecondary }}>
          <Loader2 className="h-4 w-4 animate-spin" />
          {language === 'zh' ? 'Tutor 正在思考...' : 'Tutor is thinking...'}
        </div>
      )}
    </div>
  );
}
