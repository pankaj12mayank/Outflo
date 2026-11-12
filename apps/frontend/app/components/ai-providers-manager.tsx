"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import api, { aiAPI } from "@/app/lib/api";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Cpu,
  Edit3,
  Eye,
  EyeOff,
  Globe2,
  KeyRound,
  Loader2,
  Plus,
  Power,
  RefreshCw,
  Server,
  Star,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { cn } from "@/app/lib/utils";
import { toast } from "@/app/components/toast";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Label } from "@/app/components/ui/label";
import { Select } from "@/app/components/ui/select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/app/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/app/components/ui/table";

const PROVIDER_TYPES = [
  { value: "openai", label: "OpenAI", defaultBaseUrl: "https://api.openai.com/v1" },
  { value: "anthropic", label: "Anthropic", defaultBaseUrl: "https://api.anthropic.com/v1" },
  { value: "custom", label: "Custom (OpenAI-compatible)", defaultBaseUrl: "" },
];

type Scope = "organization" | "platform";

type ProviderModel = { name: string; provider?: string };

type AIProvider = {
  id: string;
  name: string;
  provider_type: string;
  base_url?: string | null;
  api_key_configured: boolean;
  api_key_hint?: string | null;
  is_active: boolean;
  is_default: boolean;
  models: ProviderModel[];
  selected_model?: string | null;
  organization_id?: string | null;
  created_at: string;
  updated_at: string;
};

type OrganizationOption = { id: string; name: string };

type ProviderForm = {
  name: string;
  provider_type: string;
  base_url: string;
  api_key: string;
  models: ProviderModel[];
  selected_model: string;
  is_active: boolean;
  is_default: boolean;
  organization_id: string;
};

const EMPTY_FORM: ProviderForm = {
  name: "",
  provider_type: "openai",
  base_url: PROVIDER_TYPES[0].defaultBaseUrl,
  api_key: "",
  models: [],
  selected_model: "",
  is_active: true,
  is_default: false,
  organization_id: "",
};

function normalizeModels(raw: unknown): ProviderModel[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const models: ProviderModel[] = [];
  for (const item of raw) {
    let name = "";
    let provider: string | undefined;
    if (typeof item === "string") {
      name = item;
    } else if (item && typeof item === "object") {
      const record = item as Record<string, unknown>;
      name = typeof record.name === "string" ? record.name : "";
      provider = typeof record.provider === "string" ? record.provider : undefined;
    }
    const trimmed = name.trim();
    if (!trimmed || seen.has(trimmed)) continue;
    seen.add(trimmed);
    models.push(provider ? { name: trimmed, provider } : { name: trimmed });
  }
  return models;
}

function providerTypeLabel(type: string): string {
  return PROVIDER_TYPES.find((p) => p.value === type)?.label || type;
}

function defaultBaseUrl(type: string): string {
  return PROVIDER_TYPES.find((p) => p.value === type)?.defaultBaseUrl || "";
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const err = error as {
    response?: { data?: { detail?: unknown; message?: unknown } };
    message?: string;
  };
  const detail = err.response?.data?.detail ?? err.response?.data?.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((entry) => {
      if (entry && typeof entry === "object" && "msg" in entry) {
        return String((entry as { msg?: unknown }).msg ?? "");
      }
      return String(entry);
    });
    const message = parts.filter(Boolean).join(", ");
    if (message) return message;
  }
  return err.message || fallback;
}

export function AIProvidersManager({ scope = "organization" }: { scope?: Scope }) {
  const isPlatform = scope === "platform";
  const queryClient = useQueryClient();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ProviderForm>(EMPTY_FORM);
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [testingDraft, setTestingDraft] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [orgFilter, setOrgFilter] = useState<string>("all");

  const providersQuery = useQuery({
    queryKey: ["ai", "providers", scope],
    queryFn: async (): Promise<AIProvider[]> => {
      const res = await aiAPI.listProviders();
      const raw = Array.isArray(res.data) ? res.data : [];
      return raw
        .map((provider: Record<string, unknown>) => ({
          id: String(provider.id ?? ""),
          name: String(provider.name ?? ""),
          provider_type: String(provider.provider_type ?? ""),
          base_url: (provider.base_url as string | null | undefined) ?? null,
          api_key_configured: Boolean(provider.api_key_configured),
          api_key_hint: (provider.api_key_hint as string | null | undefined) ?? null,
          is_active: Boolean(provider.is_active ?? true),
          is_default: Boolean(provider.is_default),
          models: normalizeModels(provider.models),
          selected_model: (provider.selected_model as string | null | undefined) ?? null,
          organization_id: (provider.organization_id as string | null | undefined) ?? null,
          created_at: String(provider.created_at ?? ""),
          updated_at: String(provider.updated_at ?? ""),
        }))
        .filter((provider) => provider.id)
        .sort((a, b) => a.name.localeCompare(b.name));
    },
    staleTime: 15_000,
  });

  const organizationsQuery = useQuery({
    queryKey: ["organizations", "ai-provider-picker"],
    enabled: isPlatform,
    staleTime: 60_000,
    queryFn: async (): Promise<OrganizationOption[]> => {
      const res = await api.get("/api/v1/organizations", { params: { page: 1, page_size: 100 } });
      const raw =
        res.data?.organizations ?? res.data?.data ?? (Array.isArray(res.data) ? res.data : []);
      if (!Array.isArray(raw)) return [];
      return raw
        .map((org: Record<string, unknown>) => ({
          id: String(org.id ?? org._id ?? ""),
          name: String(org.name ?? org.company_name ?? "Unnamed organization"),
        }))
        .filter((org) => org.id);
    },
  });

  const providers = useMemo(() => providersQuery.data ?? [], [providersQuery.data]);
  const organizations = useMemo(() => organizationsQuery.data ?? [], [organizationsQuery.data]);
  const loading = providersQuery.isLoading;

  const orgName = (organizationId?: string | null) => {
    if (!organizationId) return "Platform-wide";
    return organizations.find((org) => org.id === organizationId)?.name || organizationId;
  };

  const visibleProviders = useMemo(() => {
    if (!isPlatform || orgFilter === "all") return providers;
    if (orgFilter === "global") return providers.filter((provider) => !provider.organization_id);
    return providers.filter((provider) => provider.organization_id === orgFilter);
  }, [isPlatform, orgFilter, providers]);

  const refreshProviders = () => queryClient.invalidateQueries({ queryKey: ["ai", "providers", scope] });

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowKey(false);
    setFormError(null);
  };

  const openCreate = () => {
    resetForm();
    setDialogOpen(true);
  };

  const openEdit = (provider: AIProvider) => {
    setEditingId(provider.id);
    setForm({
      name: provider.name,
      provider_type: provider.provider_type,
      base_url: provider.base_url || defaultBaseUrl(provider.provider_type),
      api_key: "",
      models: provider.models,
      selected_model: provider.selected_model || provider.models[0]?.name || "",
      is_active: provider.is_active,
      is_default: provider.is_default,
      organization_id: provider.organization_id || "",
    });
    setShowKey(false);
    setFormError(null);
    setDialogOpen(true);
  };

  const closeDialog = () => {
    if (saving) return;
    setDialogOpen(false);
    resetForm();
  };

  const updateForm = (patch: Partial<ProviderForm>) => {
    setForm((current) => ({ ...current, ...patch }));
    setFormError(null);
  };

  const handleProviderTypeChange = (providerType: string) => {
    updateForm({
      provider_type: providerType,
      base_url: defaultBaseUrl(providerType),
      models: [],
      selected_model: "",
    });
  };

  const handleFetchModels = async () => {
    setFetchingModels(true);
    setFormError(null);
    try {
      const res = await aiAPI.fetchModels({
        provider_id: editingId || undefined,
        provider_type: form.provider_type,
        base_url: form.base_url.trim() || undefined,
        api_key: form.api_key.trim() || undefined,
      });
      const data = res.data || {};
      const models = normalizeModels(data.models);
      if (!data.success) {
        toast.error("Could not fetch models", String(data.message || "The provider did not respond."));
        return;
      }
      const selectedModel =
        form.selected_model && models.some((model) => model.name === form.selected_model)
          ? form.selected_model
          : models[0]?.name || "";
      updateForm({ models, selected_model: selectedModel });
      toast.success(
        models.length ? `${models.length} model(s) available` : "Provider reachable",
        String(data.message || "")
      );
    } catch (error) {
      toast.error("Could not fetch models", apiErrorMessage(error, "Unknown error"));
    } finally {
      setFetchingModels(false);
    }
  };

  const handleTestDraft = async () => {
    setTestingDraft(true);
    setFormError(null);
    try {
      const res = await aiAPI.testProvider({
        provider_id: editingId || undefined,
        provider_type: form.provider_type,
        base_url: form.base_url.trim() || undefined,
        api_key: form.api_key.trim() || undefined,
        model: form.selected_model || undefined,
      });
      const data = res.data || {};
      if (data.success) {
        toast.success("Connection test passed", String(data.message || ""));
      } else {
        toast.error("Connection test failed", String(data.message || "Unknown error"));
      }
    } catch (error) {
      toast.error("Connection test failed", apiErrorMessage(error, "Unknown error"));
    } finally {
      setTestingDraft(false);
    }
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = form.name.trim();
    if (!name) {
      setFormError("Provider name is required.");
      return;
    }
    if (form.provider_type === "custom" && !form.base_url.trim()) {
      setFormError("Base URL is required for a custom provider.");
      return;
    }

    setSaving(true);
    setFormError(null);
    try {
      const payload: Record<string, unknown> = {
        name,
        provider_type: form.provider_type,
        base_url: form.base_url.trim() || undefined,
        models: form.models,
        selected_model: form.selected_model || form.models[0]?.name || null,
        is_active: form.is_active,
        is_default: form.is_default,
      };
      if (form.api_key.trim()) {
        payload.api_key = form.api_key.trim();
      }
      if (!editingId) {
        payload.organization_id = form.organization_id || null;
      }

      if (editingId) {
        await aiAPI.updateProvider(editingId, payload);
        toast.success("Provider updated", name);
      } else {
        await aiAPI.createProvider(payload);
        toast.success("Provider created", name);
      }

      setDialogOpen(false);
      resetForm();
      await refreshProviders();
    } catch (error) {
      setFormError(apiErrorMessage(error, "Failed to save provider."));
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (provider: AIProvider) => {
    setBusy(`${provider.id}:active`);
    try {
      await aiAPI.updateProvider(provider.id, { is_active: !provider.is_active });
      toast.success(provider.is_active ? "Provider deactivated" : "Provider activated", provider.name);
      await refreshProviders();
    } catch (error) {
      toast.error("Failed to update provider", apiErrorMessage(error, "Unknown error"));
    } finally {
      setBusy(null);
    }
  };

  const handleSetDefault = async (provider: AIProvider) => {
    setBusy(`${provider.id}:default`);
    try {
      await aiAPI.updateProvider(provider.id, { is_default: true, is_active: true });
      toast.success("Default provider updated", provider.name);
      await refreshProviders();
    } catch (error) {
      toast.error("Failed to set default provider", apiErrorMessage(error, "Unknown error"));
    } finally {
      setBusy(null);
    }
  };

  const handleTestSaved = async (provider: AIProvider) => {
    setBusy(`${provider.id}:test`);
    try {
      const res = await aiAPI.testProvider({ provider_id: provider.id });
      const data = res.data || {};
      if (data.success) {
        toast.success("Connection test passed", String(data.message || provider.name));
      } else {
        toast.error("Connection test failed", String(data.message || provider.name));
      }
    } catch (error) {
      toast.error("Connection test failed", apiErrorMessage(error, "Unknown error"));
    } finally {
      setBusy(null);
    }
  };

  const handleRefreshSavedModels = async (provider: AIProvider) => {
    setBusy(`${provider.id}:models`);
    try {
      const res = await aiAPI.fetchProviderModels(provider.id);
      const data = res.data || {};
      if (!data.success) {
        toast.error("Could not fetch models", String(data.message || provider.name));
        return;
      }
      const models = normalizeModels(data.models);
      toast.success(`${models.length} model(s) available`, String(data.message || provider.name));
      await refreshProviders();
    } catch (error) {
      toast.error("Could not fetch models", apiErrorMessage(error, "Unknown error"));
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async (provider: AIProvider) => {
    if (!window.confirm(`Delete the AI provider "${provider.name}"? This cannot be undone.`)) {
      return;
    }
    setBusy(`${provider.id}:delete`);
    try {
      await aiAPI.deleteProvider(provider.id);
      toast.success("Provider deleted", provider.name);
      await refreshProviders();
    } catch (error) {
      toast.error("Failed to delete provider", apiErrorMessage(error, "Unknown error"));
    } finally {
      setBusy(null);
    }
  };

  const modelOptions = useMemo(() => {
    const names = form.models.map((model) => model.name);
    if (form.selected_model && !names.includes(form.selected_model)) {
      names.unshift(form.selected_model);
    }
    return names.map((name) => ({ value: name, label: name }));
  }, [form.models, form.selected_model]);

  const organizationOptions = useMemo(
    () => [
      { value: "", label: "Platform-wide (all organizations)" },
      ...organizations.map((org) => ({ value: org.id, label: org.name })),
    ],
    [organizations]
  );

  const filterOptions = useMemo(
    () => [
      { value: "all", label: "All organizations" },
      { value: "global", label: "Platform-wide only" },
      ...organizations.map((org) => ({ value: org.id, label: org.name })),
    ],
    [organizations]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            {isPlatform ? "AI Providers" : "AI Provider Configuration"}
          </h1>
          <p className="mt-1 text-sm text-gray-400">
            {isPlatform
              ? "Manage platform-wide and organization-specific AI providers. Organization providers take priority over platform-wide ones."
              : "Manage the AI providers available to your organization, including API keys, models, and connection status."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isPlatform && (
            <div className="w-52">
              <Select
                options={filterOptions}
                value={orgFilter}
                onChange={(event) => setOrgFilter(event.target.value)}
                aria-label="Filter providers by organization"
              />
            </div>
          )}
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" />
            Add Provider
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Cpu className="h-5 w-5 text-purple-400" />
            Configured providers
          </CardTitle>
          <CardDescription>
            {providers.length === 0
              ? "No providers configured yet. Add your first AI provider to get started."
              : `${visibleProviders.length} of ${providers.length} provider${providers.length === 1 ? "" : "s"} shown.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>API key</TableHead>
                  <TableHead>Models</TableHead>
                  <TableHead>Status</TableHead>
                  {isPlatform && <TableHead>Organization</TableHead>}
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={isPlatform ? 7 : 6} className="h-32 text-center text-gray-400">
                      <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                    </TableCell>
                  </TableRow>
                ) : visibleProviders.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={isPlatform ? 7 : 6} className="h-32 text-center text-gray-400">
                      {providers.length === 0
                        ? "No providers configured. Add your first AI provider."
                        : "No providers match the selected organization."}
                    </TableCell>
                  </TableRow>
                ) : (
                  visibleProviders.map((provider) => {
                    const selectedModel = provider.selected_model;
                    const otherModels = provider.models.filter((model) => model.name !== selectedModel);
                    return (
                      <TableRow key={provider.id}>
                        <TableCell>
                          <div className="flex items-start gap-2">
                            <Server className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 font-medium text-white">
                                <span className="truncate">{provider.name}</span>
                                {provider.is_default && provider.is_active && (
                                  <Star className="h-3.5 w-3.5 shrink-0 fill-amber-400 text-amber-400" />
                                )}
                              </div>
                              <div className="max-w-[240px] truncate text-xs text-gray-500">
                                {provider.base_url || "Default endpoint"}
                              </div>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <span className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-gray-300">
                            {providerTypeLabel(provider.provider_type)}
                          </span>
                        </TableCell>
                        <TableCell>
                          {provider.api_key_configured ? (
                            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                              <KeyRound className="h-3.5 w-3.5" />
                              <span className="font-mono text-gray-400">{provider.api_key_hint || "Configured"}</span>
                            </span>
                          ) : (
                            <span className="flex items-center gap-1.5 text-xs text-gray-500">
                              <AlertCircle className="h-3.5 w-3.5" />
                              Not set
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          {provider.models.length > 0 ? (
                            <div className="flex max-w-[220px] flex-wrap gap-1">
                              {selectedModel && (
                                <span className="rounded-full bg-purple-500/15 px-2 py-0.5 text-xs text-purple-300">
                                  {selectedModel}
                                </span>
                              )}
                              {otherModels.slice(0, 2).map((model) => (
                                <span
                                  key={model.name}
                                  className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-gray-400"
                                >
                                  {model.name}
                                </span>
                              ))}
                              {otherModels.length > 2 && (
                                <span className="text-xs text-gray-500">+{otherModels.length - 2}</span>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs italic text-gray-500">No models</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-xs font-medium",
                              provider.is_active
                                ? "bg-emerald-500/15 text-emerald-400"
                                : "bg-red-500/15 text-red-400"
                            )}
                          >
                            {provider.is_active ? "Active" : "Inactive"}
                          </span>
                        </TableCell>
                        {isPlatform && (
                          <TableCell>
                            <span className="flex items-center gap-1.5 text-xs text-gray-400">
                              {provider.organization_id ? (
                                <Building2 className="h-3.5 w-3.5" />
                              ) : (
                                <Globe2 className="h-3.5 w-3.5 text-purple-300" />
                              )}
                              {orgName(provider.organization_id)}
                            </span>
                          </TableCell>
                        )}
                        <TableCell>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="outline"
                              size="icon-sm"
                              title="Test connection"
                              onClick={() => handleTestSaved(provider)}
                              disabled={busy === `${provider.id}:test`}
                            >
                              {busy === `${provider.id}:test` ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Zap className="h-3.5 w-3.5" />
                              )}
                            </Button>
                            <Button
                              variant="outline"
                              size="icon-sm"
                              title="Fetch models"
                              onClick={() => handleRefreshSavedModels(provider)}
                              disabled={busy === `${provider.id}:models`}
                            >
                              {busy === `${provider.id}:models` ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <RefreshCw className="h-3.5 w-3.5" />
                              )}
                            </Button>
                            {!provider.is_default && provider.is_active && (
                              <Button
                                variant="outline"
                                size="icon-sm"
                                title="Set as default"
                                onClick={() => handleSetDefault(provider)}
                                disabled={busy === `${provider.id}:default`}
                              >
                                {busy === `${provider.id}:default` ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Star className="h-3.5 w-3.5" />
                                )}
                              </Button>
                            )}
                            <Button
                              variant="outline"
                              size="icon-sm"
                              title="Edit provider"
                              onClick={() => openEdit(provider)}
                            >
                              <Edit3 className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant={provider.is_active ? "destructive" : "outline"}
                              size="icon-sm"
                              title={provider.is_active ? "Deactivate provider" : "Activate provider"}
                              onClick={() => handleToggleActive(provider)}
                              disabled={busy === `${provider.id}:active`}
                            >
                              {busy === `${provider.id}:active` ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Power className="h-3.5 w-3.5" />
                              )}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              title="Delete provider"
                              className="text-red-400 hover:bg-red-500/10 hover:text-red-300"
                              onClick={() => handleDelete(provider)}
                              disabled={busy === `${provider.id}:delete`}
                            >
                              {busy === `${provider.id}:delete` ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="h-3.5 w-3.5" />
                              )}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {dialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm sm:items-center"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeDialog();
          }}
        >
          <div className="relative my-8 w-full max-w-xl rounded-2xl border border-white/10 bg-[#111113] p-6 shadow-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">
                  {editingId ? "Edit AI provider" : "Add AI provider"}
                </h2>
                <p className="mt-1 text-xs text-gray-500">
                  Custom providers use the OpenAI-compatible <code>/models</code> and{" "}
                  <code>/chat/completions</code> endpoints.
                </p>
              </div>
              <Button variant="ghost" size="icon-sm" onClick={closeDialog} aria-label="Close">
                <X className="h-4 w-4" />
              </Button>
            </div>

            <form onSubmit={handleSave} className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ai-provider-name">Provider name</Label>
                  <Input
                    id="ai-provider-name"
                    value={form.name}
                    onChange={(event) => updateForm({ name: event.target.value })}
                    placeholder="e.g. My OpenAI"
                    autoFocus
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ai-provider-type">Provider type</Label>
                  <Select
                    id="ai-provider-type"
                    options={PROVIDER_TYPES.map((type) => ({ value: type.value, label: type.label }))}
                    value={form.provider_type}
                    onChange={(event) => handleProviderTypeChange(event.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="ai-provider-base-url">Base URL</Label>
                <Input
                  id="ai-provider-base-url"
                  value={form.base_url}
                  onChange={(event) => updateForm({ base_url: event.target.value })}
                  placeholder={defaultBaseUrl(form.provider_type) || "https://api.example.com/v1"}
                />
                <p className="text-xs text-gray-500">
                  Leave blank to use the default endpoint for this provider type.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="ai-provider-api-key">API key</Label>
                <div className="relative">
                  <Input
                    id="ai-provider-api-key"
                    type={showKey ? "text" : "password"}
                    value={form.api_key}
                    onChange={(event) => updateForm({ api_key: event.target.value })}
                    placeholder={editingId ? "Leave blank to keep the saved key" : "sk-..."}
                    className="pr-11"
                    autoComplete="new-password"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute right-1.5 top-1/2 -translate-y-1/2"
                    onClick={() => setShowKey((current) => !current)}
                    aria-label={showKey ? "Hide API key" : "Show API key"}
                  >
                    {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
                <p className="text-xs text-gray-500">
                  {editingId
                    ? "The stored key is never sent to the browser. Leave the field blank to keep it."
                    : "Stored securely and never returned in full after saving."}
                </p>
              </div>

              {isPlatform && !editingId && (
                <div className="space-y-2">
                  <Label htmlFor="ai-provider-organization">Organization</Label>
                  <Select
                    id="ai-provider-organization"
                    options={organizationOptions}
                    value={form.organization_id}
                    onChange={(event) => updateForm({ organization_id: event.target.value })}
                  />
                  <p className="text-xs text-gray-500">
                    Platform-wide providers are available to every organization as a fallback.
                  </p>
                </div>
              )}

              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-white">Models</p>
                    <p className="text-xs text-gray-500">
                      Fetch the model list from the provider, then pick the default model.
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleFetchModels}
                    disabled={fetchingModels}
                  >
                    {fetchingModels ? (
                      <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="mr-2 h-3.5 w-3.5" />
                    )}
                    Fetch models
                  </Button>
                </div>
                <div className="mt-3 space-y-2">
                  <Select
                    options={
                      modelOptions.length
                        ? modelOptions
                        : [{ value: "", label: "No models fetched yet" }]
                    }
                    value={form.selected_model}
                    onChange={(event) => updateForm({ selected_model: event.target.value })}
                    disabled={modelOptions.length === 0}
                    aria-label="Default model"
                  />
                  {form.models.length > 0 && (
                    <p className="text-xs text-gray-500">
                      {form.models.length} model(s) found. The selected model is used for AI generation.
                    </p>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-6">
                <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-300">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(event) =>
                      updateForm({
                        is_active: event.target.checked,
                        is_default: event.target.checked ? form.is_default : false,
                      })
                    }
                    className="h-4 w-4 rounded border-white/20 bg-transparent accent-purple-500"
                  />
                  Active
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-300">
                  <input
                    type="checkbox"
                    checked={form.is_default}
                    onChange={(event) =>
                      updateForm({
                        is_default: event.target.checked,
                        is_active: event.target.checked ? true : form.is_active,
                      })
                    }
                    className="h-4 w-4 rounded border-white/20 bg-transparent accent-purple-500"
                  />
                  Set as default
                </label>
              </div>

              {formError && (
                <div className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{formError}</span>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleTestDraft}
                  disabled={testingDraft}
                >
                  {testingDraft ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Zap className="mr-2 h-4 w-4" />
                  )}
                  Test connection
                </Button>
                <div className="flex items-center gap-2">
                  <Button type="button" variant="ghost" onClick={closeDialog} disabled={saving}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={saving}>
                    {saving ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="mr-2 h-4 w-4" />
                    )}
                    {editingId ? "Save changes" : "Create provider"}
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
