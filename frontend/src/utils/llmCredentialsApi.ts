import { apiFetch, type ApiRequestOptions } from './apiClient';

export type CredentialSource = 'user' | 'global' | 'local' | 'none';

export interface UserLLMCredential {
  provider_id: string;
  configured: boolean;
  enabled: boolean;
  is_default: boolean;
  base_url?: string | null;
  default_model?: string | null;
  api_key_fingerprint?: string | null;
  last_validated_at?: string | null;
  last_validation_error_code?: string | null;
  last_used_at?: string | null;
  updated_at?: string | null;
}

export interface SaveLLMCredentialPayload {
  api_key?: string;
  base_url?: string;
  default_model?: string;
  is_default?: boolean;
  is_enabled?: boolean;
}

export interface PatchLLMCredentialPayload {
  base_url?: string;
  default_model?: string;
  is_default?: boolean;
  is_enabled?: boolean;
}

export async function fetchLlmCredentials(
  options?: ApiRequestOptions,
): Promise<UserLLMCredential[]> {
  const data = await apiFetch<{ credentials: UserLLMCredential[] }>(
    '/api/llm/credentials',
    options,
  );
  return data.credentials;
}

export async function saveLlmCredential(
  providerId: string,
  payload: SaveLLMCredentialPayload,
  options?: ApiRequestOptions,
): Promise<UserLLMCredential> {
  const data = await apiFetch<{ credential: UserLLMCredential }>(
    `/api/llm/credentials/${providerId}`,
    {
      ...options,
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
  return data.credential;
}

export async function patchLlmCredential(
  providerId: string,
  payload: PatchLLMCredentialPayload,
  options?: ApiRequestOptions,
): Promise<UserLLMCredential> {
  if ('api_key' in (payload as Record<string, unknown>)) {
    throw new Error('API key updates must use saveLlmCredential');
  }
  const data = await apiFetch<{ credential: UserLLMCredential }>(
    `/api/llm/credentials/${providerId}`,
    {
      ...options,
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
  return data.credential;
}

export async function deleteLlmCredential(
  providerId: string,
  options?: ApiRequestOptions,
): Promise<{ deleted: boolean }> {
  return apiFetch<{ deleted: boolean }>(`/api/llm/credentials/${providerId}`, {
    ...options,
    method: 'DELETE',
  });
}

export async function testLlmCredential(
  providerId: string,
  options?: ApiRequestOptions,
): Promise<{ ok: boolean; trace_id?: string }> {
  return apiFetch<{ ok: boolean; trace_id?: string }>(`/api/llm/credentials/${providerId}/test`, {
    ...options,
    method: 'POST',
  });
}
