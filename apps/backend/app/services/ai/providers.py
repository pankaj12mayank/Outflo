from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import httpx
import time

from app.core.config import settings


@dataclass
class AIResponse:
    content: str
    model: str
    usage_tokens: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost: float = 0.0


@dataclass
class AIRequest:
    prompt: str
    system: Optional[str] = None
    model: str = settings.ai_default_model
    temperature: float = 0.7
    max_tokens: int = 500
    stream: bool = False
    timeout: int = settings.ai_timeout


class AIProvider(ABC):
    name: str = "base"
    supports_structured: bool = False

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass

    @property
    @abstractmethod
    def estimated_cost_per_1k_tokens(self) -> float:
        pass


def _clean_base_url(base_url: Optional[str], default: str) -> str:
    return (base_url or default).strip().rstrip("/")


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = _clean_base_url(base_url, "https://api.openai.com/v1")

    async def generate(self, request: AIRequest) -> AIResponse:
        start = time.perf_counter()

        async with httpx.AsyncClient(timeout=request.timeout, headers={"Authorization": f"Bearer {self.api_key}"}) as client:
            messages = []
            if request.system:
                messages.append({"role": "system", "content": request.system})
            messages.append({"role": "user", "content": request.prompt})

            payload = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }

            response = await client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

        latency = (time.perf_counter() - start) * 1000
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        return AIResponse(
            content=choice,
            model=request.model,
            usage_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency,
            cost=(total_tokens / 1000) * 0.002,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5, headers={"Authorization": f"Bearer {self.api_key}"}) as client:
                response = await client.get(f"{self.base_url}/models")
                return response.status_code == 200
        except Exception:
            return False

    @property
    def estimated_cost_per_1k_tokens(self) -> float:
        return 0.002


class AnthropicProvider(AIProvider):
    name = "anthropic"
    SUPPORTS_STRUCTURED = True

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1"):
        self.api_key = api_key
        self.base_url = _clean_base_url(base_url, "https://api.anthropic.com/v1")

    async def generate(self, request: AIRequest) -> AIResponse:
        start = time.perf_counter()

        async with httpx.AsyncClient(timeout=request.timeout, headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}) as client:
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
            if request.system:
                payload["system"] = request.system

            response = await client.post(f"{self.base_url}/messages", json=payload)
            response.raise_for_status()
            data = response.json()

        latency = (time.perf_counter() - start) * 1000
        content = data["content"][0]["text"]
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return AIResponse(
            content=content,
            model=request.model,
            usage_tokens=input_tokens + output_tokens,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            latency_ms=latency,
            cost=(input_tokens / 1e6) * 3.0 + (output_tokens / 1e6) * 15.0,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=8,
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            ) as client:
                response = await client.get(f"{self.base_url}/models")
                return response.status_code == 200
        except Exception:
            return False

    @property
    def estimated_cost_per_1k_tokens(self) -> float:
        return 0.015


class AIProviderManager:
    def __init__(self):
        self._providers: dict[str, AIProvider] = {}
        self._active_provider: Optional[str] = None
        self._models: dict[str, dict] = {}

    def register(self, name: str, provider: AIProvider):
        self._providers[name] = provider

    def set_active(self, name: str):
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not registered")
        self._active_provider = name

    def get_active(self) -> Optional[AIProvider]:
        if not self._active_provider:
            return None
        return self._providers.get(self._active_provider)

    def get_provider(self, name: str) -> Optional[AIProvider]:
        return self._providers.get(name)

    def list_providers(self) -> list[dict]:
        return [{"name": p.name, "active": p.name == self._active_provider} for p in self._providers.values()]

    def configure_models(self, models: dict[str, dict]):
        self._models = models

    def get_model_config(self, name: str) -> Optional[dict]:
        return self._models.get(name)


_provider_manager = AIProviderManager()


def get_provider_manager() -> AIProviderManager:
    return _provider_manager


def configure_providers(config: dict):
    if config.get("openai", {}).get("api_key"):
        openai_provider = OpenAIProvider(
            api_key=config["openai"]["api_key"],
            base_url=config["openai"].get("base_url", "https://api.openai.com/v1"),
        )
        _provider_manager.register("openai", openai_provider)

        if config["openai"].get("default"):
            _provider_manager.set_active("openai")

        for model_name, model_config in config["openai"].get("models", {}).items():
            _provider_manager._models[model_name] = {
                "provider": "openai",
                "temperature": model_config.get("temperature", 0.7),
                "max_tokens": model_config.get("max_tokens", 500),
                "cost_per_1k": model_config.get("cost_per_1k", 0.002),
                "enabled": model_config.get("enabled", True),
            }

    if config.get("anthropic", {}).get("api_key"):
        anthropic_provider = AnthropicProvider(
            api_key=config["anthropic"]["api_key"],
            base_url=config["anthropic"].get("base_url", "https://api.anthropic.com/v1"),
        )
        _provider_manager.register("anthropic", anthropic_provider)

        if config["anthropic"].get("default"):
            _provider_manager.set_active("anthropic")

        for model_name, model_config in config["anthropic"].get("models", {}).items():
            _provider_manager._models[model_name] = {
                "provider": "anthropic",
                "temperature": model_config.get("temperature", 0.7),
                "max_tokens": model_config.get("max_tokens", 500),
                "cost_per_1k": model_config.get("cost_per_1k", 0.015),
                "enabled": model_config.get("enabled", True),
            }