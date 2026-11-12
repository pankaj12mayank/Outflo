"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import ai, { aiAPI } from "@/app/lib/api";
import {
  Plus,
  Trash2,
  Edit3,
  Save,
  X,
  Eye,
  EyeOff,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Zap,
  Link,
  Database,
  Server,
  Cpu,
  Lock,
  Unlock,
} from "lucide-react";
import { cn } from "@/app/lib/utils";
import { toast } from "@/app/components/toast";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Label } from "@/app/components/ui/label";
import { Select } from "@/app/components/ui/select";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/app/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/app/components/ui/table";
import { Badge } from "@/app/components/ui/badge";

const PROVIDER_TYPES = [
  { value: "ollama", label: "Ollama (Local)", defaultBaseUrl: "http://localhost:11434" },
  { value: "openai", label: "OpenAI", defaultBaseUrl: "https://api.openai.com/v1" },
  { value: "anthropic", label: "Anthropic", defaultBaseUrl: "https://api.anthropic.com/v1" },
  { value: "custom", label: "Custom Provider", defaultBaseUrl: "" },
];

type AIProvider = {
  id: string;
  name: string;
  provider_type: string;
  base_url?: string;
  api_key_configured: boolean;
  is_active: boolean;
  is_default: boolean;
  models: string[];
  created_at: string;
  updated_at: string;
};

type ProviderFormData = {
  name: string;
  provider_type: string;
  base_url: string;
  api_key: string;
  is_active: boolean;
  is_default: boolean;
};

export default function AIProvidersPage() {
  const router = useRouter();
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ProviderFormData>({
    name: "",
    provider_type: "ollama",
    base_url: "",
    api_key: "",
    is_active: true,
    is_default: false,
  });
  const [showKey, setShowKey] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [fetchingId, setFetchingId] = useState<string | null>(null);
  const [fetchResult, setFetchResult] = useState<{ models: string[]; message: string } | null>(null);
  const [showModels, setShowModels] = useState<string | null>(null);

  const loadProviders = useCallback(async () => {
    setLoading(true);
    try {
      const res = await aiAPI.listProviders();
      const data = res.data || [];
      setProviders(
        data.map((p: any) => ({
          id: p.id,
          name: p.name,
          provider_type: p.provider_type,
          base_url: p.base_url,
          api_key_configured: p.api_key_configured,
          is_active: p.is_active,
          is_default: p.is_default,
          models: p.models || [],
          created_at: p.created_at,
          updated_at: p.updated_at,
        }))
      );
    } catch (err: any) {
      toast.error("Failed to load providers", err.response?.data?.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProviders();
  }, [loadProviders]);

  const providerTypeInfo = (type: string) => PROVIDER_TYPES.find((p) => p.value === type);

  const resetForm = () => {
    setForm({
      name: "",
      provider_type: "ollama",
      base_url: "",
      api_key: "",
      is_active: true,
      is_default: false,
    });
    setShowKey(false);
    setEditingId(null);
  };

  const handleOpen = (provider?: AIProvider) => {
    if (provider) {
      setEditingId(provider.id);
      setForm({
        name: provider.name,
        provider_type: provider.provider_type,
        base_url: provider.base_url || providerTypeInfo(provider.provider_type)?.defaultBaseUrl || "",
        api_key: "",
        is_active: provider.is_active,
        is_default: provider.is_default,
      });
    } else {
      resetForm();
    }
    setOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        name: form.name,
        provider_type: form.provider_type,
        base_url: form.base_url || undefined,
        api_key: form.api_key || undefined,
        is_active: form.is_active,
        is_default: form.is_default,
      };

      if (editingId) {
        await aiAPI.updateProvider(editingId, payload);
        toast.success("Provider updated");
      } else {
        await aiAPI.createProvider(payload);
        toast.success("Provider created");
      }

      setOpen(false);
      await loadProviders();
    } catch (err: any) {
      toast.error("Failed to save provider", err.response?.data?.detail || err.response?.data?.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleActive = async (provider: AIProvider) => {
    setLoading(true);
    try {
      await aiAPI.updateProvider(provider.id, {
        is_active: !provider.is_active,
      });
      toast.success(`Provider ${!provider.is_active ? "activated" : "deactivated"}`);
      await loadProviders();
    } catch (err: any) {
      toast.error("Failed to update provider", err.response?.data?.detail || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this AI provider? This cannot be undone.")) return;
    setLoading(true);
    try {
      await aiAPI.deleteProvider(id);
      toast.success("Provider deleted");
      await loadProviders();
    } catch (err: any) {
      toast.error("Failed to delete provider", err.response?.data?.detail || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async (id: string) => {
    const provider = providers.find((p) => p.id === id);
    if (!provider) return;
    setTestingId(id);
    try {
      const res = await aiAPI.testProvider({
        provider_type: provider.provider_type,
        base_url: provider.base_url,
        api_key: provider.api_key_configured ? "test" : undefined,
      });
      const data = res.data;
      if (data.success) {
        toast.success("Connection test passed", data.message);
      } else {
        toast.error("Connection test failed", data.message);
      }
    } catch (err: any) {
      toast.error("Connection test failed", err.response?.data?.message || "Unknown error");
    } finally {
      setTestingId(null);
    }
  };

  const handleFetchModels = async (id: string) => {
    const provider = providers.find((p) => p.id === id);
    if (!provider) return;
    setFetchingId(id);
    try {
      const res = await aiAPI.fetchProviderModels(id);
      const data = res.data;
      setFetchResult({ models: data.models?.map((m: any) => m.name || m) || [], message: data.message || "" });
      setShowModels(id);
    } catch (err: any) {
      setFetchResult({ models: [], message: err.response?.data?.message || "Failed to fetch models" });
      setShowModels(id);
    } finally {
      setFetchingId(null);
    }
  };

  const handleSaveModel = async (id: string, modelName: string) => {
    const provider = providers.find((p) => p.id === id);
    if (!provider) return;
    try {
      await aiAPI.updateProvider(id, { name: provider.name });
      toast.success(`Model "${modelName}" noted`);
    } catch {
      toast.error("Failed to set default model");
    }
  };

  const statusBadge = (active: boolean) => (
    <Badge variant={active ? "secondary" : "destructive"} className="w-8 text-xs">
      {active ? "Active" : "Inactive"}
    </Badge>
  );

  const defaultBadge = (isDefault: boolean) => (
    <Badge variant="secondary" className="w-10 text-xs">
      {isDefault ? "Default" : "—"}
    </Badge>
  );

  return (
    <div className="space-y-6 p-4 sm:p-6 md:p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">AI Provider Configuration</h1>
          <p className="text-gray-400 text-sm">Manage AI providers, API keys, models, and connection status.</p>
        </div>
        <Button onClick={() => handleOpen()} className="px-4 py-2">
          <Plus className="w-4 h-4 mr-2" /> Add Provider
        </Button>
      </div>

      {/* Providers Table */}
      <Card>
        <CardHeader>
          <CardTitle>Configured Providers</CardTitle>
          <CardDescription>
            Add and manage AI providers for your organization.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">Name</TableHead>
                  <TableHead className="w-20">Type</TableHead>
                  <TableHead className="w-32">Base URL</TableHead>
                  <TableHead className="w-20">API Key</TableHead>
                  <TableHead className="w-16">Status</TableHead>
                  <TableHead className="w-12">Default</TableHead>
                  <TableHead className="w-20">Models</TableHead>
                  <TableHead className="w-24">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {providers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="h-32 text-center text-gray-400">
                      No providers configured. Add your first AI provider.
                    </TableCell>
                  </TableRow>
                ) : (
                  providers.map((provider) => (
                    <TableRow key={provider.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <TableCell className="font-medium text-sm">{provider.name}</TableCell>
                      <TableCell className="text-sm">
                        <Badge variant="outline" className="text-xs px-2 py-1">
                          {providerTypeInfo(provider.provider_type)?.label || provider.provider_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-gray-400 truncate max-w-[200px]">
                        {provider.base_url || "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        <span className={cn("flex items-center gap-2", provider.api_key_configured ? "" : "text-gray-500")}>
                          {provider.api_key_configured ? (
                            <>
                              <span className="text-xs font-mono text-green-400">{Array(12).join("*")}</span>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 p-0"
                                onClick={(e) => { e.stopPropagation(); setShowKey(!showKey); }}
                              >
                                {showKey ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                              </Button>
                            </>
                          ) : (
                            <span className="text-xs text-gray-500">Not set</span>
                          )}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm">{statusBadge(provider.is_active)}</TableCell>
                      <TableCell className="text-sm">{defaultBadge(provider.is_default)}</TableCell>
                      <TableCell className="text-sm">
                        {provider.models.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {provider.models.slice(0, 3).map((m) => (
                              <Badge key={m} variant="secondary" className="text-xs px-2 py-1">
                                {m}
                              </Badge>
                            ))}
                            {provider.models.length > 3 && <span className="text-xs text-gray-500">+{provider.models.length - 3}</span>}
                          </div>
                        ) : (
                          <span className="text-xs text-gray-500 italic">No models</span>
                        )}
                        {provider.is_active && provider.models.length === 0 && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleFetchModels(provider.id)}
                            disabled={fetchingId === provider.id}
                            className="mt-1 h-6 px-2 text-xs"
                          >
                            {fetchingId === provider.id ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              <RefreshCw className="w-3 h-3" />
                            )}
                          </Button>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); handleTest(provider.id); }}
                            disabled={testingId === provider.id}
                            className="h-7 px-2 text-xs"
                          >
                            {testingId === provider.id ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              <Zap className="w-3 h-3" />
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); handleOpen(provider); }}
                            className="h-7 px-2 text-xs"
                          >
                            <Edit3 className="w-3 h-3" />
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); handleDelete(provider.id); }}
                            className="h-7 px-2 text-xs"
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 p-0 text-xs"
                            onClick={(e) => { e.stopPropagation(); setShowModels(showModels === provider.id ? null : provider.id); }}
                          >
                            <Cpu className="w-3 h-3" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Models Detail (inline popover-style) */}
      {showModels && fetchResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setShowModels(null)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="relative w-full max-w-md bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Fetched Models</h3>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setShowModels(null)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <p className="text-sm text-gray-400 mb-4">{fetchResult.models.length} models found. {fetchResult.message}</p>
            <div className="space-y-2 max-h-60 overflow-y-auto pr-2">
              {fetchResult.models.map((m, i) => (
                <div key={i} className="flex items-center justify-between p-2 rounded border border-white/5">
                  <span className="text-sm text-gray-300">{m}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 p-0 text-xs"
                    onClick={(e) => { e.stopPropagation(); handleSaveModel(providers.find((p) => p.id === showModels)?.id || "", m); }}
                  >
                    <CheckCircle className="w-3 h-3" />
                  </Button>
                </div>
              ))}
              {fetchResult.models.length === 0 && (
                <p className="text-xs text-gray-400 italic text-center">{fetchResult.message}</p>
              )}
            </div>
            <div className="mt-4 flex justify-end">
              <Button variant="outline" onClick={() => setShowModels(null)}>Done</Button>
            </div>
          </div>
        </div>
      )}

      {/* Add/Edit Dialog (inline modal) */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="relative w-full max-w-md bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">{editingId ? "Edit AI Provider" : "Add AI Provider"}</h3>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setOpen(false)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Provider Name</Label>
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. My Ollama"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label>Provider Type</Label>
                  <Select
                    options={PROVIDER_TYPES.map((p) => ({ value: p.value, label: p.label }))}
                    value={form.provider_type}
                    onChange={(e) => {
                      const val = e.target.value;
                      const info = PROVIDER_TYPES.find((p) => p.value === val);
                      setForm({ ...form, provider_type: val, base_url: info?.defaultBaseUrl || "" });
                    }}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label>Base URL</Label>
                <Input
                  value={form.base_url}
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  placeholder={providerTypeInfo(form.provider_type)?.defaultBaseUrl || "https://api.example.com/v1"}
                />
                <p className="text-xs text-gray-500">
                  Endpoint for the provider API.
                </p>
              </div>
              <div className="space-y-2">
                <Label>API Key</Label>
                <div className="relative">
                  <Input
                    type={showKey ? "text" : "password"}
                    value={form.api_key}
                    onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                    placeholder="sk-..."
                    className="pr-10"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6 p-0 text-xs"
                    onClick={() => setShowKey(!showKey)}
                  >
                    {showKey ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                  </Button>
                </div>
                <p className="text-xs text-gray-500">
                  Stored securely. Hidden after saving.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-purple)] focus:ring-[var(--color-purple)] bg-[var(--color-bg-primary)]"
                  />
                  <Label className="text-sm text-gray-300 cursor-pointer">Active</Label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.is_default}
                    onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                    className="w-4 h-4 rounded border-[var(--color-border)] text-[var(--color-purple)] focus:ring-[var(--color-purple)] bg-[var(--color-bg-primary)]"
                  />
                  <Label className="text-sm text-gray-300 cursor-pointer">Set as Default</Label>
                </div>
              </div>
            </form>
            <div className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {editingId ? "Save Changes" : "Create Provider"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
