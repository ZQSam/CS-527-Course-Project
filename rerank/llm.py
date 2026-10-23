"""Model providers: Anthropic Messages API and a deterministic offline fake for tests."""

import json
import time


def call_cost(usage: dict, price: dict) -> float:
    """Dollar cost from response usage; thinking tokens are billed inside output_tokens."""
    input_tokens = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) * 1.25 \
        + usage.get("cache_read_input_tokens", 0) * 0.1
    return (input_tokens * price["input"] + usage.get("output_tokens", 0) * price["output"]) / 1_000_000


def request_params(model: str, effort: str, max_tokens: int, system: str, messages: list, schema: dict) -> dict:
    """Messages API parameters shared by direct calls and Message Batches requests.

    Thinking stays at the model default (adaptive); effort is the cost/quality control.
    No server-side refusal fallback: answers from a different model would contaminate results.
    """
    return {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages,
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}}}


def response_record(message, latency_s) -> dict:
    """Normalize an SDK Message (direct or from a batch result) into the cached response shape."""
    text = "".join(block.text for block in message.content if block.type == "text")
    usage = message.usage
    return {
        "text": text,
        "stop_reason": message.stop_reason,
        "stop_details": message.stop_details.to_dict() if getattr(message, "stop_details", None) else None,
        "response_model": message.model,
        "request_id": getattr(message, "_request_id", None),
        "latency_s": latency_s,
        "usage": {
            "input_tokens": usage.input_tokens or 0,
            "output_tokens": usage.output_tokens or 0,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None) or 0,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None) or 0,
        },
    }


class ProviderError(RuntimeError):
    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, effort: str, max_tokens: int, timeout: float = 300.0):
        import anthropic  # deferred so offline tests and dry runs need no SDK
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(timeout=timeout, max_retries=3)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def complete(self, system: str, messages: list, schema: dict, cache_key: str = None) -> dict:
        anthropic = self._anthropic
        started = time.monotonic()
        try:
            response = self.client.messages.create(
                **request_params(self.model, self.effort, self.max_tokens, system, messages, schema))
        except anthropic.AuthenticationError as error:
            raise ProviderError(f"authentication failed: {error.message}", "auth") from error
        except anthropic.BadRequestError as error:
            raise ProviderError(f"bad request: {error.message}", "bad_request") from error
        except anthropic.RateLimitError as error:
            raise ProviderError(f"rate limited after retries: {error.message}", "rate_limit") from error
        except anthropic.APIStatusError as error:
            raise ProviderError(f"API status {error.status_code}: {error.message}", "api_status") from error
        except anthropic.APIConnectionError as error:
            raise ProviderError(f"connection error: {error}", "connection") from error
        return response_record(response, round(time.monotonic() - started, 3))


class FakeProvider:
    """Offline provider: ranks labels by a scripted policy so tests and dry runs never touch the network."""

    name = "fake"

    def __init__(self, model: str = "fake-model", policy: str = "reverse", script=None, stop_reason: str = "end_turn"):
        self.model = model
        self.effort = "none"
        self.max_tokens = 0
        self.policy = policy
        self.script = list(script or [])
        self.stop_reason = stop_reason
        self.calls = 0

    def complete(self, system: str, messages: list, schema: dict, cache_key: str = None) -> dict:
        self.calls += 1
        labels = schema["properties"]["ranking"]["items"]["enum"]
        if self.script:
            text = self.script.pop(0)
        else:
            ranking = list(reversed(labels)) if self.policy == "reverse" else list(labels)
            text = json.dumps({"ranking": ranking,
                               "top3_reasons": [{"candidate": label, "reason": self.reason_for(label, messages)}
                                                for label in ranking[:3]]})
        prompt_chars = len(system) + sum(len(m["content"]) for m in messages)
        return {"text": text, "stop_reason": self.stop_reason, "stop_details": None, "response_model": self.model,
                "request_id": None, "latency_s": 0.0,
                "usage": {"input_tokens": prompt_chars // 4, "output_tokens": len(text) // 4,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}

    @staticmethod
    def reason_for(label: str, messages: list) -> str:
        """Cite the first '>>' stack line shown for the label (else its first line) so the evidence gate has input."""
        prompt = messages[0]["content"]
        section = prompt.split(f"## {label}\n", 1)[1].split("\n## ", 1)[0] if f"## {label}\n" in prompt else ""
        numbers = [line[2:].split("|", 1)[0].strip() for line in section.splitlines()
                   if "|" in line and line[2:].split("|", 1)[0].strip().isdigit()]
        marked = [line[2:].split("|", 1)[0].strip() for line in section.splitlines() if line.startswith(">>")]
        cited = (marked or numbers or [None])[0]
        return f"fake (L{cited})" if cited else "fake"
