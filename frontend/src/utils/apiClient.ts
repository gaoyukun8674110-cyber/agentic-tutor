export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';

export interface ApiRequestOptions extends RequestInit {
  signal?: AbortSignal;
  skipAuthRefresh?: boolean;
}

type UiLanguage = 'zh' | 'en';

let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export class ApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(message: string, status: number, code: string, traceId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.traceId = traceId;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

function getCurrentUiLanguage(): UiLanguage {
  if (typeof window !== 'undefined') {
    if (window.localStorage.getItem('ai-tutor-language') === 'en') return 'en';
    if (document.body.dataset.lang === 'en') return 'en';
  }
  return 'zh';
}

function getAcceptLanguageValue(language: UiLanguage): string {
  return language === 'en' ? 'en-US' : 'zh-CN';
}

const englishToChineseMessages: Record<string, string> = {
  'Authentication is required. Please sign in.': '需要身份验证。请先登录。',
  'You do not have permission for this action.': '你没有权限执行此操作。',
  'Missing access token': '缺少访问令牌',
  'Invalid access token': '访问令牌无效',
  'Access token expired': '访问令牌已过期',
  'Invalid credentials': '用户名或密码错误',
  'User is not authorized for this resource': '当前用户无权访问该资源',
  'Model provider is temporarily unavailable': '模型服务暂时不可用',
  'Request failed': '请求失败',
  'Internal error': '内部错误',
  'Task not found': '任务不存在',
  'Conversation not found': '会话不存在',
  'Question not found': '题目不存在',
  'No more questions or session ended': '没有更多题目，或训练已结束',
  'Failed to fetch': '请求失败，请检查网络或后端服务。',
  'NetworkError when attempting to fetch resource.': '请求失败，请检查网络或后端服务。',
  'Unexpected error': '发生了意外错误。',
};

function localizeClientMessage(message: string, language = getCurrentUiLanguage()): string {
  if (!message) return language === 'zh' ? '发生了意外错误。' : 'Unexpected error';
  if (language === 'en') return message;
  return englishToChineseMessages[message] ?? message;
}

export function getDefaultErrorMessage(): string {
  return localizeClientMessage('Unexpected error');
}

export function getUserFacingError(error: unknown): string {
  const language = getCurrentUiLanguage();

  if (error instanceof ApiError) {
    if (error.status === 401) return localizeClientMessage('Authentication is required. Please sign in.', language);
    if (error.status === 403) return localizeClientMessage('You do not have permission for this action.', language);
    if (error.status >= 500) {
      console.error('Server error', { code: error.code, traceId: error.traceId, message: error.message });
      const localizedMessage = localizeClientMessage(error.message, language);
      return error.traceId ? `${localizedMessage} (trace ${error.traceId})` : localizedMessage;
    }
    return localizeClientMessage(error.message, language);
  }
  return error instanceof Error ? localizeClientMessage(error.message, language) : getDefaultErrorMessage();
}

export async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    let code = response.status >= 500 ? 'server_error' : 'request_error';
    let traceId = response.headers.get('X-Trace-Id') || undefined;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') {
        detail = body.detail;
      } else if (body.detail && typeof body.detail === 'object') {
        detail = body.detail.user_message || detail;
        code = body.detail.code || code;
        traceId = body.detail.trace_id || traceId;
      }
    } catch {
      // Keep HTTP status text when the backend does not return JSON.
    }
    throw new ApiError(detail, response.status, code, traceId);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function isAuthPath(path: string): boolean {
  return path.startsWith('/api/auth/');
}

function buildHeaders(options: ApiRequestOptions, token = accessToken): Headers {
  const headers = new Headers(options.headers);
  if (!headers.has('Content-Type') && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (!headers.has('Accept-Language')) {
    headers.set('Accept-Language', getAcceptLanguageValue(getCurrentUiLanguage()));
  }
  return headers;
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Accept-Language': getAcceptLanguageValue(getCurrentUiLanguage()) },
      });
      if (!response.ok) {
        accessToken = null;
        return null;
      }
      const payload = await parseJsonResponse<{ access_token: string }>(response);
      accessToken = payload.access_token;
      return accessToken;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

async function fetchWithHeaders(path: string, options: ApiRequestOptions, token = accessToken): Promise<Response> {
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: buildHeaders(options, token),
  });
}

export async function apiFetch<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  let response = await fetchWithHeaders(path, options);

  if (response.status === 401 && !options.skipAuthRefresh && !isAuthPath(path)) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      response = await fetchWithHeaders(path, { ...options, skipAuthRefresh: true }, refreshedToken);
    } else if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('auth:logout'));
    }
  }

  return parseJsonResponse<T>(response);
}

export async function apiUpload<T>(path: string, body: FormData, options: ApiRequestOptions = {}): Promise<T> {
  const uploadOptions = { ...options, method: options.method || 'POST', body };
  return apiFetch<T>(path, uploadOptions);
}
