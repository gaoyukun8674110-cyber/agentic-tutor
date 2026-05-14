import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, KeyRound, Save, Star, Trash2 } from 'lucide-react';
import { TopNavbar } from '../components/TopNavbar';
import { Button } from '../components/ui/button';
import { fetchChatProviders, type ChatProvider } from '../utils/chatApi';
import { cardSurfaceStyle, primaryActionStyle, statusPanelStyle } from '../utils/glassStyles';
import {
  deleteLlmCredential,
  fetchLlmCredentials,
  patchLlmCredential,
  saveLlmCredential,
  type UserLLMCredential,
} from '../utils/llmCredentialsApi';
import { getUserFacingError } from '../utils/apiClient';
import { useSettings } from '../utils/settings';

interface ProviderFormState {
  apiKey: string;
  baseUrl: string;
  defaultModel: string;
  isDefault: boolean;
  isEnabled: boolean;
}

const emptyForm: ProviderFormState = {
  apiKey: '',
  baseUrl: '',
  defaultModel: '',
  isDefault: false,
  isEnabled: true,
};

function sourceLabel(provider: ChatProvider, credential?: UserLLMCredential): string {
  if (credential?.configured) return 'Your key';
  if (provider.source === 'global') return 'Demo key';
  if (provider.source === 'local') return 'Local';
  return 'Not configured';
}

export function SettingsModelPage() {
  const { tokens, textStyle, t } = useSettings();
  const queryClient = useQueryClient();
  const [selectedProviderId, setSelectedProviderId] = useState('linkapi');
  const [forms, setForms] = useState<Record<string, ProviderFormState>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const providersQuery = useQuery({
    queryKey: ['llm', 'providers'],
    queryFn: ({ signal }) => fetchChatProviders({ signal }),
    retry: false,
  });
  const credentialsQuery = useQuery({
    queryKey: ['llm', 'credentials'],
    queryFn: ({ signal }) => fetchLlmCredentials({ signal }),
    retry: false,
  });

  const providers = providersQuery.data ?? [];
  const credentialsByProvider = useMemo(() => {
    const map = new Map<string, UserLLMCredential>();
    for (const credential of credentialsQuery.data ?? []) {
      map.set(credential.provider_id, credential);
    }
    return map;
  }, [credentialsQuery.data]);
  const selectedProvider = providers.find((provider) => provider.id === selectedProviderId) ?? providers[0];
  const selectedCredential = selectedProvider ? credentialsByProvider.get(selectedProvider.id) : undefined;
  const form = selectedProvider ? forms[selectedProvider.id] ?? emptyForm : emptyForm;

  const refreshCredentials = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['llm', 'credentials'] }),
      queryClient.invalidateQueries({ queryKey: ['llm', 'providers'] }),
    ]);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProvider) return null;
      const saved = await saveLlmCredential(selectedProvider.id, {
        api_key: form.apiKey,
        base_url: form.baseUrl || undefined,
        default_model: form.defaultModel || undefined,
        is_default: form.isDefault,
        is_enabled: form.isEnabled,
      });
      return saved;
    },
    onSuccess: async () => {
      if (selectedProvider) {
        setForms((current) => ({
          ...current,
          [selectedProvider.id]: { ...form, apiKey: '' },
        }));
      }
      setError(null);
      setMessage(t('已保存模型凭证', 'Model credential saved'));
      await refreshCredentials();
    },
    onError: (mutationError) => {
      setMessage(null);
      setError(getUserFacingError(mutationError));
    },
  });

  const patchMutation = useMutation({
    mutationFn: async (updates: Partial<ProviderFormState>) => {
      if (!selectedProvider) return null;
      const nextForm = { ...form, ...updates };
      setForms((current) => ({ ...current, [selectedProvider.id]: nextForm }));
      return patchLlmCredential(selectedProvider.id, {
        base_url: nextForm.baseUrl || undefined,
        default_model: nextForm.defaultModel || undefined,
        is_default: nextForm.isDefault,
        is_enabled: nextForm.isEnabled,
      });
    },
    onSuccess: async () => {
      setError(null);
      setMessage(t('已更新模型设置', 'Model settings updated'));
      await refreshCredentials();
    },
    onError: (mutationError) => {
      setMessage(null);
      setError(getUserFacingError(mutationError));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProvider) return null;
      return deleteLlmCredential(selectedProvider.id);
    },
    onSuccess: async () => {
      if (selectedProvider) {
        setForms((current) => ({ ...current, [selectedProvider.id]: emptyForm }));
      }
      setError(null);
      setMessage(t('已删除模型凭证', 'Model credential deleted'));
      await refreshCredentials();
    },
    onError: (mutationError) => {
      setMessage(null);
      setError(getUserFacingError(mutationError));
    },
  });

  const updateForm = (updates: Partial<ProviderFormState>) => {
    if (!selectedProvider) return;
    setForms((current) => ({
      ...current,
      [selectedProvider.id]: { ...(current[selectedProvider.id] ?? emptyForm), ...updates },
    }));
  };

  const selectProvider = (provider: ChatProvider) => {
    setSelectedProviderId(provider.id);
    const credential = credentialsByProvider.get(provider.id);
    setForms((current) => ({
      ...current,
      [provider.id]: current[provider.id] ?? {
        apiKey: '',
        baseUrl: credential?.base_url ?? '',
        defaultModel: credential?.default_model ?? provider.default_model,
        isDefault: Boolean(credential?.is_default),
        isEnabled: credential?.enabled ?? true,
      },
    }));
  };

  return (
    <div className="relative min-h-screen overflow-hidden" style={{ ...textStyle, color: tokens.textPrimary }}>
      <div className="fixed inset-0" style={{ background: tokens.pageGradient }} />
      <div className="fixed inset-0" style={{ background: tokens.overlayGradient }} />
      <TopNavbar />

      <main className="relative mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 xl:px-0">
        <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold">{t('模型配置', 'Model settings')}</h1>
            <p className="mt-2 text-sm" style={{ color: tokens.textSecondary }}>
              {t('保存个人 provider 凭证后，Tutor 会优先使用你的 Key。', 'Saved provider credentials are used before demo fallback keys.')}
            </p>
          </div>
          <KeyRound className="h-9 w-9" style={{ color: tokens.accentPrimary }} />
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-2xl border px-4 py-3 text-sm" style={statusPanelStyle(tokens, 'warning')}>
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </div>
        )}
        {message && (
          <div className="mb-4 flex items-start gap-2 rounded-2xl border px-4 py-3 text-sm" style={statusPanelStyle(tokens, 'success')}>
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            {message}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="space-y-3">
            {providers.map((provider) => {
              const credential = credentialsByProvider.get(provider.id);
              const isSelected = selectedProvider?.id === provider.id;
              return (
                <button
                  key={provider.id}
                  onClick={() => selectProvider(provider)}
                  className="w-full rounded-2xl border px-4 py-3 text-left transition-colors"
                  style={{
                    ...cardSurfaceStyle(tokens),
                    borderColor: isSelected ? tokens.accentPrimary : 'var(--ai-border-subtle)',
                  }}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold">{provider.name}</p>
                      <p className="text-xs" style={{ color: tokens.textSecondary }}>
                        {sourceLabel(provider, credential)}
                      </p>
                    </div>
                    {credential?.is_default && <Star className="h-4 w-4" style={{ color: tokens.warning }} />}
                  </div>
                </button>
              );
            })}
          </aside>

          <section className="rounded-2xl p-6 shadow-lg" style={cardSurfaceStyle(tokens)}>
            {selectedProvider ? (
              <div className="space-y-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-2xl font-semibold">{selectedProvider.name}</h2>
                    <p className="text-sm" style={{ color: tokens.textSecondary }}>
                      {selectedProvider.adapter} · {sourceLabel(selectedProvider, selectedCredential)}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      onClick={() => patchMutation.mutate({ isDefault: true })}
                      disabled={!selectedCredential || selectedCredential.is_default || patchMutation.isPending}
                      className="rounded-xl"
                      style={cardSurfaceStyle(tokens)}
                    >
                      <Star className="h-4 w-4" />
                      {t('设为默认', 'Set default')}
                    </Button>
                    <Button
                      onClick={() => deleteMutation.mutate()}
                      disabled={!selectedCredential || deleteMutation.isPending}
                      className="rounded-xl"
                      style={cardSurfaceStyle(tokens)}
                    >
                      <Trash2 className="h-4 w-4" />
                      {t('删除', 'Delete')}
                    </Button>
                  </div>
                </div>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium">{t('API Key', 'API key')}</span>
                  <input
                    value={form.apiKey}
                    onChange={(event) => updateForm({ apiKey: event.target.value })}
                    placeholder={selectedCredential ? t('留空则不显示旧 Key', 'Leave blank; saved keys are never shown') : 'sk-...'}
                    className="w-full rounded-xl border px-3 py-2 outline-none"
                    style={{ background: tokens.surface, borderColor: 'var(--ai-border-subtle)', color: tokens.textPrimary }}
                    type="password"
                    autoComplete="off"
                  />
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium">Base URL</span>
                  <input
                    value={form.baseUrl}
                    onChange={(event) => updateForm({ baseUrl: event.target.value })}
                    placeholder={selectedCredential?.base_url || t('留空使用后端默认 Base URL', 'Leave blank to use backend default Base URL')}
                    className="w-full rounded-xl border px-3 py-2 outline-none"
                    style={{ background: tokens.surface, borderColor: 'var(--ai-border-subtle)', color: tokens.textPrimary }}
                  />
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium">{t('默认模型', 'Default model')}</span>
                  <input
                    value={form.defaultModel}
                    onChange={(event) => updateForm({ defaultModel: event.target.value })}
                    list="llm-models"
                    placeholder={selectedProvider.default_model}
                    className="w-full rounded-xl border px-3 py-2 outline-none"
                    style={{ background: tokens.surface, borderColor: 'var(--ai-border-subtle)', color: tokens.textPrimary }}
                  />
                  <datalist id="llm-models">
                    {selectedProvider.models.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                </label>

                <div className="flex flex-wrap gap-4">
                  <label className="inline-flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.isDefault}
                      onChange={(event) => updateForm({ isDefault: event.target.checked })}
                    />
                    {t('设为 auto 默认 provider', 'Use as auto default provider')}
                  </label>
                  <label className="inline-flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.isEnabled}
                      onChange={(event) => updateForm({ isEnabled: event.target.checked })}
                    />
                    {t('启用', 'Enabled')}
                  </label>
                </div>

                <div className="flex flex-wrap gap-3">
                  <Button
                    onClick={() => saveMutation.mutate()}
                    disabled={saveMutation.isPending || (selectedProvider.id !== 'ollama' && !form.apiKey.trim())}
                    className="rounded-xl"
                    style={primaryActionStyle(tokens)}
                  >
                    <Save className="h-4 w-4" />
                    {t('保存凭证', 'Save credential')}
                  </Button>
                  <Button
                    onClick={() => patchMutation.mutate({})}
                    disabled={!selectedCredential || patchMutation.isPending}
                    className="rounded-xl"
                    style={cardSurfaceStyle(tokens)}
                  >
                    {t('仅更新设置', 'Update settings only')}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="text-sm" style={{ color: tokens.textSecondary }}>
                {providersQuery.isLoading || credentialsQuery.isLoading
                  ? t('正在加载模型配置...', 'Loading model settings...')
                  : t('没有可用 provider。', 'No providers available.')}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
