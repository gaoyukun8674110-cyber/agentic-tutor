import { apiFetch, apiUpload, type ApiRequestOptions } from './apiClient';

export interface ChatProvider {
  id: string;
  name: string;
  adapter: string;
  enabled: boolean;
  implemented: boolean;
  default_model: string;
  models: string[];
  source?: 'user' | 'global' | 'local' | 'none';
  configured?: boolean;
  credential_updated_at?: string | null;
  reason?: string | null;
}

export interface PromptProfile {
  id: string;
  name: string;
  description: string;
}

export const FALLBACK_PROMPT_PROFILES: PromptProfile[] = [
  {
    id: 'three_stage',
    name: '三段式学习法',
    description: '先规划核心知识，再解释概念，最后用费曼追问检测理解。',
  },
  {
    id: 'socratic',
    name: '苏格拉底引导',
    description: '通过问题一步步引导你自己发现解法。',
  },
  {
    id: 'explain',
    name: '概念讲解',
    description: '用简单语言和例子解释知识点。',
  },
  {
    id: 'diagnose',
    name: '错因诊断',
    description: '检查答案并定位薄弱点。',
  },
  {
    id: 'coach',
    name: '学习教练',
    description: '安排下一步学习行动。',
  },
  {
    id: 'exam',
    name: '考试训练',
    description: '按考试节奏进行限时训练。',
  },
  {
    id: 'custom',
    name: '自定义提示词',
    description: '使用你输入的系统提示词。',
  },
];

export type LearningPhase = 'planning' | 'understanding' | 'feynman' | 'general';

export interface ChatMessagePayload {
  role: 'user' | 'assistant' | 'system';
  content: string;
  label?: string | null;
  id?: string | number;
  created_at?: string;
}

export interface TutorChatRequest {
  conversation_id?: number | null;
  provider: string;
  model?: string;
  prompt_profile: string;
  system_prompt_override?: string | null;
  messages: ChatMessagePayload[];
  tutor_context: Record<string, unknown>;
}

export interface TutorChatResponse {
  message: ChatMessagePayload;
  messages?: ChatMessagePayload[];
  provider: string;
  model: string;
  prompt_profile: string;
  learning_phase?: LearningPhase | string;
  conversation_id?: number;
  conversation?: TutorConversationSummary;
  exchange_count?: number;
  should_suggest_new_chat?: boolean;
  should_start_new_chat?: boolean;
  summary_generated?: boolean;
  context_policy?: 'full' | 'summary_recent' | string;
  material_context?: MaterialContext;
  material_context_error?: string | null;
  usage?: Record<string, number | null>;
  latency_ms?: number;
  credential_source?: 'user' | 'global' | 'local';
  credential_fingerprint?: string | null;
}

export interface TutorConversationSummary {
  id: number;
  title: string;
  preview: string;
  training_mode?: string | null;
  prompt_profile?: string | null;
  provider?: string | null;
  model?: string | null;
  message_count: number;
  exchange_count?: number;
  should_suggest_new_chat?: boolean;
  should_start_new_chat?: boolean;
  summary?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TutorConversationDetail extends TutorConversationSummary {
  messages: ChatMessagePayload[];
}

export interface TutorConversationExport {
  filename: string;
  content: string;
}

export interface StudyMaterial {
  id: number;
  user_id?: string | null;
  filename: string;
  file_type: string;
  content_type?: string | null;
  status: string;
  error?: string | null;
  char_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface MaterialSearchResult {
  chunk_id?: number;
  material_id: number;
  filename?: string;
  source_label: string;
  content: string;
  score: number;
  embedding_mode?: 'hash' | 'openai' | string;
}

export interface MaterialContext {
  chunks: MaterialSearchResult[];
  embedding_mode?: 'hash' | 'openai' | string;
}

export interface MaterialSearchResponse {
  chunks: MaterialSearchResult[];
  embedding_mode: 'hash' | 'openai' | string;
}

export async function fetchChatProviders(options?: ApiRequestOptions): Promise<ChatProvider[]> {
  const data = await apiFetch<{ providers: ChatProvider[] }>('/api/llm/providers', options);
  return data.providers;
}

export async function fetchPromptProfiles(options?: ApiRequestOptions): Promise<PromptProfile[]> {
  const data = await apiFetch<{ profiles: PromptProfile[] }>('/api/llm/prompt-profiles', options);
  return data.profiles;
}

export async function sendTutorChat(
  request: TutorChatRequest,
  options?: ApiRequestOptions,
): Promise<TutorChatResponse> {
  return apiFetch<TutorChatResponse>('/api/llm/chat', {
    ...options,
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function fetchTutorConversations(
  options?: ApiRequestOptions,
): Promise<TutorConversationSummary[]> {
  const data = await apiFetch<{ conversations: TutorConversationSummary[] }>(
    '/api/llm/conversations',
    options,
  );
  return data.conversations;
}

export async function searchTutorConversations(
  query: string,
  options?: ApiRequestOptions,
): Promise<TutorConversationSummary[]> {
  const params = new URLSearchParams({ query });
  const data = await apiFetch<{ conversations: TutorConversationSummary[] }>(
    `/api/llm/conversations/search?${params.toString()}`,
    options,
  );
  return data.conversations;
}

export async function fetchTutorConversation(
  conversationId: number,
  options?: ApiRequestOptions,
): Promise<TutorConversationDetail> {
  return apiFetch<TutorConversationDetail>(`/api/llm/conversations/${conversationId}`, options);
}

export async function deleteTutorConversation(
  conversationId: number,
  options?: ApiRequestOptions,
): Promise<{ deleted: boolean }> {
  return apiFetch<{ deleted: boolean }>(`/api/llm/conversations/${conversationId}`, {
    ...options,
    method: 'DELETE',
  });
}

export async function exportTutorConversation(
  conversationId: number,
  options?: ApiRequestOptions,
): Promise<TutorConversationExport> {
  return apiFetch<TutorConversationExport>(
    `/api/llm/conversations/${conversationId}/export`,
    options,
  );
}

export async function fetchStudyMaterials(options?: ApiRequestOptions): Promise<StudyMaterial[]> {
  const data = await apiFetch<{ materials: StudyMaterial[] }>('/api/materials', options);
  return data.materials;
}

export async function uploadStudyMaterial(
  file: File,
  options?: ApiRequestOptions,
): Promise<StudyMaterial> {
  const formData = new FormData();
  formData.append('file', file);
  return apiUpload<StudyMaterial>('/api/materials/upload', formData, options);
}

export async function searchStudyMaterials(
  query: string,
  materialIds?: number[],
  options?: ApiRequestOptions,
): Promise<MaterialSearchResponse> {
  return apiFetch<MaterialSearchResponse>('/api/materials/search', {
    ...options,
    method: 'POST',
    body: JSON.stringify({
      query,
      material_ids: materialIds,
    }),
  });
}
