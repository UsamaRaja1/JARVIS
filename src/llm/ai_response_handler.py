import ast
import json
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from google import genai
from groq import Groq
from openai import OpenAI

from src.utilz.logger import logger_

load_dotenv()


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip().lower() for item in value.split(",") if item.strip()]


openai_client = None
if api_key := os.getenv("OPENAI_API_KEY"):
    openai_client = OpenAI(api_key=api_key)

openrouter_client = None
if openrouter_api_key := os.getenv("OPENROUTER_API_KEY"):
    openrouter_client = OpenAI(
        api_key=openrouter_api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )

groq_client = None
if groq_api_key := os.getenv("GROQ_API_KEY"):
    groq_client = Groq()

gemini_client = None
if gemini_api_key := os.getenv("GEMINI_API_KEY"):
    gemini_client = genai.Client(api_key=gemini_api_key)

MODEL_REGISTRY = {
    "gpt-3.5": {
        "api_name": "gpt-3.5-turbo-0125",
        "provider": "openai",
        "api_type": "chat",
    },
    "gpt-4": {
        "api_name": "gpt-4-0125-preview",
        "provider": "openai",
        "api_type": "chat",
    },
    "gpt-4o": {
        "api_name": "gpt-4o",
        "provider": "openai",
        "api_type": "chat",
    },
    "gpt-4o-mini": {
        "api_name": "gpt-4o-mini",
        "provider": "openai",
        "api_type": "chat",
    },
    "gpt-4.1": {
        "api_name": "gpt-4.1",
        "provider": "openai",
        "api_type": "chat",
    },
    "gpt-5-mini": {
        "api_name": "gpt-5-mini",
        "provider": "openai",
        "api_type": "responses",
    },
}

SUPPORTED_PROVIDERS = ("openrouter", "groq", "gemini", "openai")


def resolve_model_config(model: str) -> dict:
    """
    Dynamically determine API config from model name.
    """

    # Responses API models (modern)
    if model.startswith(("openrouter/",)):
        return {
            "api_name": model.removeprefix("openrouter/"),
            "provider": "openrouter",
            "api_type": "chat",
        }
    elif model.startswith(("gpt-4.1", "gpt-5", "o")):
        return {
            "api_name": model,
            "provider": "openai",
            "api_type": "responses",
        }
    elif model.startswith(("gemini",)):
        return {
            "api_name": model,
            "provider": "gemini",
            "api_type": "chat",
        }
    elif model.startswith(("llama", "mixtral", "gemma", "qwen", "openai/")):
        return {
            "api_name": model,
            "provider": "groq",
            "api_type": "chat",
        }

    # Chat completions (legacy)
    return {
        "api_name": model,
        "provider": "openai",
        "api_type": "chat",
    }


@dataclass
class ModelUsage:
    requests: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class UsageTracker:
    def __init__(self, pricing: dict):
        self.pricing = pricing
        self.usage: dict[str, ModelUsage] = defaultdict(ModelUsage)

    def add(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ):
        u = self.usage[model]
        u.requests += 1
        u.input_tokens += input_tokens
        u.output_tokens += output_tokens

        price = self.pricing.get(model, {})
        u.cost += self.calculate_cost(
            price=price,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        )

    def calculate_cost(
        self,
        price: dict,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> float:
        """
        Calculate USD cost using per-million token pricing.
        """

        input_cost = input_tokens * price.get("input", 0)
        cached_cost = cached_input_tokens * price.get("cached_input", 0)
        output_cost = output_tokens * price.get("output", 0)

        total_cost = (input_cost + cached_cost + output_cost) / 1_000_000

        return round(total_cost, 8)

    def get(self, model: str | None = None) -> dict:
        if model:
            u = self.usage[model]
            return {
                "model": model,
                "requests": u.requests,
                "input_tokens": u.input_tokens,
                "cached_input_tokens": u.cached_input_tokens,
                "output_tokens": u.output_tokens,
                "total_tokens": u.input_tokens + u.output_tokens,
                "cost": round(u.cost, 6),
            }

        # combined usage
        total = ModelUsage()
        usage_dict = {}
        for m, u in self.usage.items():
            total.requests += u.requests
            total.input_tokens += u.input_tokens
            total.cached_input_tokens += u.cached_input_tokens
            total.output_tokens += u.output_tokens
            total.cost += u.cost
            usage_dict[m] = {
                "requests": u.requests,
                "input_tokens": u.input_tokens,
                "cached_input_tokens": u.cached_input_tokens,
                "output_tokens": u.output_tokens,
                "total_tokens": u.input_tokens + u.output_tokens,
                "cost": round(u.cost, 6),
            }

        return {
            "all": {
                "model": "ALL",
                "requests": total.requests,
                "input_tokens": total.input_tokens,
                "cached_input_tokens": total.cached_input_tokens,
                "output_tokens": total.output_tokens,
                "total_tokens": total.input_tokens + total.output_tokens,
                "cost": round(total.cost, 6),
            },
            "per_model": usage_dict,
        }


class ConversationAI:
    def __init__(self, default_model: str):
        self.default_model = default_model
        self.data_dir = os.getenv("DATA_DIR", "/tmp/data")
        self.provider_mode = os.getenv("LLM_PROVIDER", "auto").strip().lower()
        self.provider_order = self._normalize_provider_order(env_list("LLM_PROVIDER_ORDER", ["openrouter", "groq", "gemini", "openai"]))
        self.provider_models = {
            "openrouter": os.getenv("LLM_OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            "openai": os.getenv("LLM_OPENAI_MODEL", "gpt-4o"),
            "groq": os.getenv("LLM_GROQ_MODEL", default_model),
            "gemini": os.getenv("LLM_GEMINI_MODEL", "gemini-2.5-flash"),
        }
        self.pricing_path = "src/data/pricing.json"
        self.usage_path = os.path.join(self.data_dir, "openai_usage_cost.jsonl")
        os.makedirs(self.data_dir, exist_ok=True)

        with open(self.pricing_path) as f:
            pricing = json.load(f)["prices"]

        self.usage_tracker = UsageTracker(pricing)
        self.cost_history: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        task: str | None = None,
        reasoning: dict[str, Any] | None = None,
    ) -> dict:
        attempts = self._build_provider_attempts(model)
        last_error = None

        for index, (provider, selected_model) in enumerate(attempts, start=1):
            try:
                return self._chat_with_provider(
                    provider=provider,
                    messages=messages,
                    model=selected_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    task=task,
                    reasoning=reasoning,
                )
            except Exception as e:
                last_error = e
                if index == len(attempts):
                    raise
                next_provider, next_model = attempts[index]
                logger_.warning(f"LLM provider {provider} failed for model {selected_model}: {e}. Trying {next_provider} with model {next_model}.")

        if last_error:
            raise last_error
        raise RuntimeError("No LLM providers configured")

    def _chat_with_provider(
        self,
        provider: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        task: str | None = None,
        reasoning: dict[str, Any] | None = None,
    ) -> dict:
        cfg = resolve_model_config(model)

        if provider == "groq":
            return self.groq_chat(
                messages,
                model=cfg["api_name"],
                max_tokens=max_tokens,
                temperature=temperature,
                task=task,
            )

        if provider == "gemini":
            return self.gemini_chat(
                messages,
                model=cfg["api_name"],
                max_tokens=max_tokens,
                temperature=temperature,
                task=task,
            )

        if provider == "openrouter":
            return self.openrouter_chat(
                messages,
                model=cfg["api_name"],
                max_tokens=max_tokens,
                temperature=temperature,
                task=task,
            )

        return self.openai_chat(
            messages,
            model=cfg["api_name"],
            api_type=cfg["api_type"],
            max_tokens=max_tokens,
            temperature=temperature,
            task=task,
            reasoning=reasoning,
        )

    def openai_chat(
        self,
        messages: list[dict],
        model: str,
        api_type: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        task: str | None = None,
        reasoning: dict[str, Any] | None = None,
    ) -> dict:
        start = time.time()

        task = task or "openai_chat"

        if not openai_client:
            raise RuntimeError("OpenAI API key not set")

        if api_type == "chat":
            response = openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cached_input_tokens = 0

            if hasattr(response.usage, "input_tokens_details"):
                cached_input_tokens = getattr(response.usage.input_tokens_details, "cached_tokens", 0)
            content = response.choices[0].message.content

        elif api_type == "responses":
            response = openai_client.responses.create(model=model, input=messages, reasoning=reasoning, max_output_tokens=max_tokens, prompt_cache_key=task)

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cached_input_tokens = 0

            if hasattr(response.usage, "input_tokens_details"):
                cached_input_tokens = getattr(response.usage.input_tokens_details, "cached_tokens", 0)
            content = response.output_text

        else:
            raise RuntimeError("Unknown API type")

        # Compute cost for this request
        self._record_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            task=task,
        )

        logger_.info(f"{task} | {model} | {(time.time() - start):.3f} sec")

        content = robust_json_loads(content)

        return {
            "content": content,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def groq_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        task: str | None = None,
    ) -> dict:
        if not groq_client:
            raise RuntimeError("GROQ API key not set")
        model = model or self.default_model
        start = time.time()

        response = groq_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content

        # Groq currently may not always return usage reliably
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        # Track usage (optional fallback pricing)
        self._record_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            task=task or "groq_chat",
        )

        logger_.info(f"{task or 'groq_chat'} | {model} | {(time.time() - start):.3f} sec")

        content = robust_json_loads(content)

        return {
            "content": content,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def gemini_chat(
        self,
        messages: list[dict],
        model: str = "gemini-2.5-flash",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        task: str | None = None,
    ):
        if not gemini_client:
            raise RuntimeError("GEMINI_API_KEY not set")

        start = time.time()

        # Convert OpenAI messages into Gemini format
        prompt = "\n".join(f"{m['role']}: {self._stringify_message_content(m.get('content'))}" for m in messages)

        response = gemini_client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )

        content = response.text
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0)
        output_tokens = getattr(usage, "candidates_token_count", 0)

        self._record_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            task=task or "gemini_chat",
        )

        logger_.info(f"{task or 'gemini_chat'} | {model} | {(time.time() - start):.3f} sec")

        return {
            "content": robust_json_loads(content),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def openrouter_chat(
        self,
        messages: list[dict],
        model: str = "openai/gpt-4o-mini",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        task: str | None = None,
    ) -> dict:
        if not openrouter_client:
            raise RuntimeError("OPENROUTER_API_KEY not set")

        start = time.time()

        response = openrouter_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        cached_input_tokens = 0

        self._record_usage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            task=task or "openrouter_chat",
        )

        logger_.info(f"{task or 'openrouter_chat'} | {model} | {(time.time() - start):.3f} sec")

        return {
            "content": robust_json_loads(content),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        task: str = "chat",
    ) -> None:
        price = self.usage_tracker.pricing.get(model, {})
        cost = self.usage_tracker.calculate_cost(
            price=price,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        )

        self.usage_tracker.add(
            model,
            input_tokens,
            output_tokens,
            cached_input_tokens=cached_input_tokens,
        )

        usage_entry = {
            "model": model,
            "task": task,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost": cost,
            "timestamp": time.time(),
        }
        self.cost_history.append(usage_entry)

        with open(self.usage_path, "a") as f:
            f.write(json.dumps(usage_entry) + "\n")

    def _build_provider_attempts(self, model: str | None) -> list[tuple[str, str]]:
        attempts: list[tuple[str, str]] = []

        if model:
            cfg = resolve_model_config(model)
            attempts.append((cfg["provider"], cfg["api_name"]))
            if self.provider_mode == "auto":
                for provider in self.provider_order:
                    if provider != cfg["provider"]:
                        attempts.append((provider, self.provider_models[provider]))
            return self._filter_available_attempts(attempts)

        if self.provider_mode in SUPPORTED_PROVIDERS:
            return self._filter_available_attempts([(self.provider_mode, self.provider_models[self.provider_mode])])

        return self._filter_available_attempts([(provider, self.provider_models[provider]) for provider in self.provider_order])

    def _filter_available_attempts(self, attempts: list[tuple[str, str]]) -> list[tuple[str, str]]:
        filtered: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for provider, model in attempts:
            if provider not in SUPPORTED_PROVIDERS:
                continue
            if not self._provider_is_available(provider):
                continue
            attempt = (provider, model)
            if attempt in seen:
                continue
            seen.add(attempt)
            filtered.append(attempt)

        return filtered

    def _normalize_provider_order(self, providers: list[str]) -> list[str]:
        normalized = [provider for provider in providers if provider in SUPPORTED_PROVIDERS]
        for provider in SUPPORTED_PROVIDERS:
            if provider not in normalized:
                normalized.append(provider)
        return normalized

    @staticmethod
    def _provider_is_available(provider: str) -> bool:
        if provider == "openai":
            return openai_client is not None
        if provider == "openrouter":
            return openrouter_client is not None
        if provider == "groq":
            return groq_client is not None
        if provider == "gemini":
            return gemini_client is not None
        return False

    @staticmethod
    def _stringify_message_content(content: Any) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                    elif item.get("type") == "image_url":
                        parts.append("[image]")
                    else:
                        parts.append(json.dumps(item))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part)

        if isinstance(content, dict):
            return json.dumps(content)

        return str(content)

    def get_usage(self, model: str | None = None) -> dict:
        return {**self.usage_tracker.get(model), "detailed": self.get_cost_history()}

    def get_cost_history(self) -> list[dict[str, Any]]:
        """Return the per-request cost history"""
        return self.cost_history

    def get_usage_history(self) -> list[dict[str, Any]]:
        """Return the per-request cost history"""
        data = []
        if os.path.exists(self.usage_path):
            with open(self.usage_path) as f:
                data = f.readlines()
                data = [json.loads(o.strip().strip("\n")) for o in data]
        return data


def get_json_from_str(string: str):
    try:
        pattern = r"\s*\{.*?\}\s*"
        match = re.search(pattern, string, re.DOTALL)
        if match:
            json_str = match.group().strip()
            json_data = json.loads(json_str)  # Parse the JSON string into a dictionary
            return json_data
        else:
            return {"error": f"No json found in string: {string}"}
    except Exception as e:
        return {"error": f"Unable to parse string: {string}\nerror: {e}"}


def robust_json_loads(raw_response):
    if not raw_response or isinstance(raw_response, dict):
        return raw_response

    response = raw_response.strip()
    response = re.sub(r"```json|```", "", response)
    if response.lower().startswith("json"):
        response = response[4:].strip()

    try:
        return json.loads(response)
    except Exception as e:
        logger_.error(f"Failed to parse JSON with json.loads: {e}")

    match = re.search(r"\{.*\}", response, re.DOTALL)
    if not match:
        return raw_response
    json_part = match.group()

    # Remove trailing commas (common LLM issue)
    json_part = re.sub(r",\s*}", "}", json_part)
    json_part = re.sub(r",\s*]", "]", json_part)

    # Try normal JSON parsing
    try:
        return json.loads(json_part)
    except json.JSONDecodeError:
        pass

    # Fallback: handle single quotes
    try:
        return ast.literal_eval(json_part)
    except Exception as e:
        logger_.error(f"Failed to parse JSON: {e}")
        return raw_response


if __name__ == "__main__":
    groq_models = [
        "openai/gpt-oss-120b",
        "groq/compound-mini",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-20b",
        "canopylabs/orpheus-v1-english",
        "moonshotai/kimi-k2-instruct",
        "openai/gpt-oss-safeguard-20b",
        "moonshotai/kimi-k2-instruct-0905",
        "whisper-large-v3-turbo",
        "meta-llama/llama-prompt-guard-2-86m",
        "allam-2-7b",
        "whisper-large-v3",
        "meta-llama/llama-prompt-guard-2-22m",
        "qwen/qwen3-32b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "groq/compound",
        "llama-3.3-70b-versatile",
        "canopylabs/orpheus-arabic-saudi",
    ]

    ai = ConversationAI("gpt-4o")
    response = ai.groq_chat([{"role": "user", "content": "Hello, how are you?"}], model=groq_models[-2])
    print(response)
