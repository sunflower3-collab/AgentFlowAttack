"""LLM clients for the executor E. The conductor only knows the method complete(prompt) -> LLMResponse."""
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    text: str
    usage: dict = field(default_factory=dict)  # fields as in openai CompletionUsage
    model: str | None = None
    system_fingerprint: str | None = None
    finish_reason: str | None = None
    response_id: str | None = None


class StubLLM:
    """Test double: returns a preset reply and records the prompts."""

    def __init__(self, reply="executed"):
        self.reply = reply
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return LLMResponse(text=self.reply)


class OpenAIClient:
    """Adapter to the openai SDK (Chat Completions). The SDK reads the key only from OPENAI_API_KEY."""

    def __init__(self, model, temperature=0, seed=None, max_completion_tokens=None):
        from openai import OpenAI  # imported here so the stub tests do not depend on the SDK

        self._client = OpenAI(max_retries=0, timeout=60.0)  # no hidden retries; 60s timeout instead of the default 600
        self.model = model
        self.params = {"temperature": temperature}
        if seed is not None:
            self.params["seed"] = seed
        if max_completion_tokens is not None:
            self.params["max_completion_tokens"] = max_completion_tokens

    def complete(self, prompt):
        response = self._client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}], **self.params
        )
        return LLMResponse(
            text=response.choices[0].message.content,
            usage=response.usage.model_dump() if response.usage else {},
            model=response.model,
            system_fingerprint=response.system_fingerprint,
            finish_reason=response.choices[0].finish_reason,
            response_id=response.id,
        )
