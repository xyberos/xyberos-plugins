"""The OpenAI-compatible adapter: one chat and embedding shape, many services.

Every OpenAI-compatible endpoint — a hosted vendor, or a gateway such as LiteLLM, vLLM, or Ollama's
own compatibility routes — speaks the same three routes, so one adapter covers all of them and the
differences stay in configuration rather than in code. Xyberos keeps every wire format inside this
module: nothing above it names a vendor or a field of ``/chat/completions``.

An injected ``httpx.AsyncClient`` is used as given and never closed, which is how tests drive the
adapter through ``httpx.MockTransport`` and how applications share a connection pool.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from logging import Logger, getLogger
from typing import cast
from urllib.parse import urlsplit

try:
    import httpx
except ModuleNotFoundError as error:  # pragma: no cover - a broken install, not a code path
    raise ModuleNotFoundError(
        "xyberos-openai-compatible needs httpx, which this distribution declares as a dependency: "
        f"reinstall it with 'pip install \"xyberos-openai-compatible\"' ({error})"
    ) from error

from xyberos.ai.contracts import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    FinishReason,
    Message,
    ModelCapabilities,
    ModelHealth,
    ModelStatus,
    Role,
    ToolCall,
    ToolSpec,
    Usage,
)
from xyberos.errors import (
    AIConfigurationError,
    AIInvalidPayloadError,
    AIModelNotFoundError,
    AIRateLimitError,
    AIRequestError,
    AITimeoutError,
    AITransportError,
    AIUnsupportedCapabilityError,
)

DEFAULT_BASE_URL = "http://127.0.0.1:59080/v1"
DEFAULT_MODEL_ENV_HINT = "XYBEROS_AI__OPENAI_COMPATIBLE__MODEL"
EMBEDDING_MODEL_ENV_HINT = "XYBEROS_AI__OPENAI_COMPATIBLE__EMBEDDING_MODEL"
CHAT_PATH = "/chat/completions"
EMBEDDINGS_PATH = "/embeddings"
MODELS_PATH = "/models"
_LOGGER_NAME = "xyberos.ai.openai_compatible"
_RETRYABLE_STATUSES = frozenset({408, 409, 429})
"""Statuses that report a busy or unlucky service rather than a bad request."""


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    """Configuration for one OpenAI-compatible endpoint.

    ``model`` is required: Xyberos never chooses a model, and never downloads one. Capability claims
    are explicit and default to the conservative side, because an endpoint accepting a request field
    does not mean the model honours it.
    """

    model: str
    base_url: str = DEFAULT_BASE_URL
    api_key: str = field(default="", repr=False)
    """Never rendered. A dataclass repr would put the key into the first log line that prints the
    settings, and a log is the easiest place to lose a credential from. The ``Authorization`` header
    is the only place it is used."""

    embedding_model: str | None = None
    timeout: float | None = 60.0
    connect_timeout: float | None = 5.0
    retry_attempts: int = 2
    """How many times a single chat or embedding call may be sent. ``1`` disables retrying, which is
    what a deployment that pays per attempt should choose."""

    retry_base_delay: float = 0.2
    chat: bool = True
    """A deployment that serves embeddings only sets this to ``false``, and every chat call is then
    refused with a reason instead of being attempted."""

    tools: bool = False
    structured_output: bool = False
    streaming: bool = True
    embeddings: bool = False

    def __post_init__(self) -> None:
        _validate_model(self.model)
        _validate_base_url(self.base_url)
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        _validate_embedding_model(self.embedding_model)
        for label, value in (("timeout", self.timeout), ("connect_timeout", self.connect_timeout)):
            if value is not None and value <= 0:
                raise AIConfigurationError(f"{label} must be greater than zero, got {value!r}")
        if self.retry_attempts < 1:
            raise AIConfigurationError(
                f"retry_attempts must be at least 1 (it counts attempts, not retries), got "
                f"{self.retry_attempts!r}"
            )
        if self.retry_base_delay < 0:
            raise AIConfigurationError("retry_base_delay must not be negative")
        for label, value in (
            ("chat", self.chat),
            ("tools", self.tools),
            ("structured_output", self.structured_output),
            ("streaming", self.streaming),
            ("embeddings", self.embeddings),
        ):
            _validate_flag(value, label)

    @property
    def capabilities(self) -> ModelCapabilities:
        """Return the capabilities these settings claim."""
        return ModelCapabilities(
            tools=self.tools,
            structured_output=self.structured_output,
            streaming=self.streaming,
            embeddings=self.embeddings,
        )

    def endpoint(self, path: str) -> str:
        """Join ``path`` onto the base URL.

        A base URL is given with or without a trailing slash depending on who wrote it down, so both
        are joined the same way and neither produces a doubled separator.
        """
        _validate_path(path)
        return f"{self.base_url}/{path.lstrip('/')}"

    @property
    def safe_base_url(self) -> str:
        """The base URL without credentials, for a log line or an error message.

        The API key is not part of the URL, but a gateway sometimes carries a token of its own in the
        query string. The keys stay readable — they are what a reader is looking for — and the values
        do not, because a query value is where a credential hides when it is not the API key.
        """
        parts = urlsplit(self.base_url)
        host = parts.hostname or ""
        if parts.port is not None:
            host = f"{host}:{parts.port}"
        safe = f"{parts.scheme}://{host}{parts.path}"
        if parts.query:
            keys = [pair.partition("=")[0] for pair in parts.query.split("&")]
            safe = f"{safe}?" + "&".join(f"{key}=***" for key in keys)
        return safe


def _require_settings(value: object) -> OpenAICompatibleSettings:
    """Return ``value`` as settings, refusing anything else.

    A settings object arrives from composition or from untyped configuration, and this is the one
    place where an adapter states what it needs: everything below reads the settings through it.
    """
    if not isinstance(value, OpenAICompatibleSettings):
        raise AIConfigurationError(
            f"expected OpenAICompatibleSettings, got {type(value).__name__}"
        )
    return value


def _validate_model(model: object) -> None:
    """Reject anything that cannot name a chat model, and never echo the value.

    The field is annotated ``str``, but settings are built from parsed configuration, where a
    mistyped value is exactly the failure this catches before a request is ever attempted.
    """
    if not isinstance(model, str) or not model.strip():
        raise AIConfigurationError(
            "an OpenAI-compatible adapter needs an explicit model: Xyberos never chooses a model "
            f"for you, so set it in configuration, for example {DEFAULT_MODEL_ENV_HINT}=gpt-4o-mini"
        )


def _validate_embedding_model(embedding_model: object) -> None:
    """Reject an embedding model name that cannot be used; ``None`` means none was configured."""
    if embedding_model is None:
        return
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise AIConfigurationError("embedding_model must be a non-empty model name")


def _validate_flag(value: object, label: str) -> None:
    """Reject a capability claim that is not a boolean, rather than trusting the annotation.

    The whole point of a declared capability is that it was decided deliberately, so a value such as
    ``"yes"`` from a configuration file is refused here instead of being read as truthy.
    """
    if not isinstance(value, bool):
        raise AIConfigurationError(f"{label} must be true or false, got {value!r}")


def _validate_path(path: object) -> None:
    """Reject an endpoint path that cannot be joined onto the base URL."""
    if not isinstance(path, str) or not path.strip():
        raise AIConfigurationError("an endpoint path must be a non-empty string")


def _validate_base_url(base_url: object) -> None:
    """Reject anything that is not a plain http(s) URL, and never echo the value.

    Credentials are checked first, because the check that rejects them must win over the one that
    describes the value: a URL such as ``https://token@host/v1`` would otherwise be quoted in the
    message, which is exactly what the credential rule exists to prevent. No branch echoes the input
    for the same reason — a free-form string from configuration is the one thing here that may hold a
    secret, so the messages state the expected shape instead.
    """
    if not isinstance(base_url, str) or not base_url.strip():
        raise AIConfigurationError("base_url must be a non-empty URL")
    parts = urlsplit(base_url)
    if parts.username or parts.password:
        raise AIConfigurationError(
            "base_url must not embed credentials, because they would reach logs and error "
            "messages; put the key in api_key instead"
        )
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise AIConfigurationError(
            f"base_url must be an http(s) URL with a host, for example {DEFAULT_BASE_URL}"
        )


@dataclass
class _StreamState:
    """The one thing a stream carries between lines: the usage block the service sends last."""

    usage: Usage | None = None


class OpenAICompatibleProvider:
    """An OpenAI-compatible adapter implementing chat, streaming, embeddings, and readiness."""

    def __init__(
        self,
        settings: OpenAICompatibleSettings,
        *,
        client: httpx.AsyncClient | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._settings = _require_settings(settings)
        self._http = client
        self._owns_client = client is None
        self._logger = logger or getLogger(_LOGGER_NAME)

    @property
    def name(self) -> str:
        """Return the adapter name."""
        return "openai-compatible"

    @property
    def model(self) -> str:
        """Return the configured chat model."""
        return self._settings.model

    @property
    def settings(self) -> OpenAICompatibleSettings:
        """Return the settings this adapter was built with."""
        return self._settings

    @property
    def capabilities(self) -> ModelCapabilities:
        """Return the capabilities these settings claim."""
        return self._settings.capabilities

    async def aclose(self) -> None:
        """Close the client this adapter owns. An injected client is left alone."""
        if self._http is None or not self._owns_client:
            return
        client, self._http = self._http, None
        await client.aclose()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Return one completed chat response."""
        self._require_supported(request)
        data = await self._post(CHAT_PATH, self._chat_payload(request, stream=False))
        return self._chat_response(data)

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """Stream a chat response.

        This adapter streams content; tools and response schemas are refused on a streaming request
        rather than streamed as a payload nothing can validate yet.
        """
        self._require_supported(request, streaming=True)
        if request.tools:
            raise AIRequestError("an OpenAI-compatible streaming request cannot offer tools")
        if request.response_schema is not None:
            raise AIRequestError("an OpenAI-compatible streaming request cannot ask for a schema")
        return self._stream(request)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return embeddings for the requested inputs."""
        if not self._settings.capabilities.embeddings:
            raise AIUnsupportedCapabilityError(
                f"the OpenAI-compatible model {self._settings.model!r} is not configured with "
                "embedding support; set embeddings = true once you have confirmed the endpoint "
                "serves embeddings",
                capability="embeddings",
                model=self._settings.model,
            )
        model = request.model or self._settings.embedding_model
        if not model:
            raise AIConfigurationError(
                "no embedding model is configured; set embedding_model on the settings, for example "
                f"{EMBEDDING_MODEL_ENV_HINT}=text-embedding-3-small"
            )
        data = await self._post(EMBEDDINGS_PATH, {"model": model, "input": list(request.inputs)})
        return self._embedding_response(data, inputs=len(request.inputs), model=model)

    async def health(self) -> ModelHealth:
        """Report whether the endpoint is reachable and the configured model is listed.

        A health check reports problems rather than raising them, and it distinguishes the two
        failures a caller has to act on differently: an endpoint that answers nothing, and one that
        answers without the configured model. ``GET /models`` is the OpenAI API's own listing route,
        so a service that does not implement it cannot be asked about its models at all, and saying
        so is better than reporting ready on a guess.
        """
        safe_url = self._settings.safe_base_url
        try:
            response = await self._client().get(
                self._settings.endpoint(MODELS_PATH), headers=self._headers()
            )
        except httpx.TimeoutException as error:
            return ModelHealth(
                status=ModelStatus.UNREACHABLE,
                model=self._settings.model,
                detail=(
                    f"the endpoint at {safe_url} did not answer {MODELS_PATH} in time "
                    f"({type(error).__name__})"
                ),
            )
        except httpx.HTTPError as error:
            return ModelHealth(
                status=ModelStatus.UNREACHABLE,
                model=self._settings.model,
                detail=f"the endpoint at {safe_url} is unreachable ({type(error).__name__})",
            )
        version = response.headers.get("openai-version") or None
        if response.status_code in {401, 403}:
            return ModelHealth(
                status=ModelStatus.UNHEALTHY,
                model=self._settings.model,
                detail=(
                    f"the endpoint at {safe_url} rejected the configured api_key with "
                    f"{response.status_code}"
                ),
                provider_version=version,
            )
        if response.status_code == 404:
            return ModelHealth(
                status=ModelStatus.UNHEALTHY,
                model=self._settings.model,
                detail=(
                    f"the service at {safe_url} does not answer {MODELS_PATH}, so its models cannot "
                    "be listed; check that base_url names the API root, including any /v1 suffix"
                ),
                provider_version=version,
            )
        if response.status_code >= 400:
            return ModelHealth(
                status=ModelStatus.UNHEALTHY,
                model=self._settings.model,
                detail=f"the service answered {response.status_code} for {MODELS_PATH}",
                provider_version=version,
            )
        listed = _model_ids(_safe_json(response))
        if listed and self._settings.model not in listed:
            shown = ", ".join(listed[:5])
            more = f" and {len(listed) - 5} more" if len(listed) > 5 else ""
            return ModelHealth(
                status=ModelStatus.MODEL_UNAVAILABLE,
                model=self._settings.model,
                detail=(
                    f"the service at {safe_url} does not list the model "
                    f"{self._settings.model!r}; it lists: {shown}{more}, and Xyberos never downloads "
                    "or loads a model for you"
                ),
                provider_version=version,
            )
        return ModelHealth(
            status=ModelStatus.READY,
            model=self._settings.model,
            provider_version=version,
        )

    def _require_supported(self, request: ChatRequest, *, streaming: bool = False) -> None:
        """Refuse a request the settings do not claim, instead of sending one that may be ignored."""
        if not self._settings.chat:
            raise AIUnsupportedCapabilityError(
                f"this adapter is configured with chat = false for {self._settings.model!r}; it "
                "serves embeddings only",
                capability="chat",
                model=self._settings.model,
            )
        if streaming and not self._settings.capabilities.streaming:
            raise AIUnsupportedCapabilityError(
                f"the OpenAI-compatible model {self._settings.model!r} is configured with "
                "streaming = false; enable it once you have confirmed the endpoint streams",
                capability="streaming",
                model=self._settings.model,
            )
        if request.tools and not self._settings.capabilities.tools:
            raise AIUnsupportedCapabilityError(
                f"the OpenAI-compatible model {self._settings.model!r} is not configured with tool "
                "support; set tools = true once you have confirmed the model honours a tool "
                "declaration",
                capability="tools",
                model=self._settings.model,
            )
        if request.response_schema is not None and not self._settings.capabilities.structured_output:
            raise AIUnsupportedCapabilityError(
                f"the OpenAI-compatible model {self._settings.model!r} is not configured with "
                "structured output support; set structured_output = true once you have confirmed "
                "the endpoint honours a JSON schema",
                capability="structured_output",
                model=self._settings.model,
            )

    async def _post(self, path: str, payload: Mapping[str, object]) -> dict[str, object]:
        """Send one request, retrying only the failures a later attempt can fix.

        A rejected key, a malformed request, and a wrong path are the caller's to fix, so they are
        raised on the first attempt; a timeout, a rate limit, and a server error are the service's
        and are retried within the configured budget.
        """
        url = self._settings.endpoint(path)
        client = self._client()
        self._logger.debug("openai-compatible call path=%s model=%s", path, payload.get("model"))
        for attempt in range(1, self._settings.retry_attempts + 1):
            try:
                response = await client.post(url, json=payload, headers=self._headers())
            except httpx.TimeoutException as error:
                failure: AITransportError = AITimeoutError(
                    f"the call to {path} timed out ({type(error).__name__})"
                )
            except httpx.HTTPError as error:
                failure = AITransportError(
                    f"the service is unreachable: {type(error).__name__}"
                )
            else:
                try:
                    self._raise_for_status(response, path)
                except AITransportError as error:
                    # A timeout, a rate limit, and a server error: all retryable by class.
                    failure = error
                else:
                    data = _decode_object(response.text, source=f"the {path} response")
                    self._raise_for_error_field(data)
                    return data
            if attempt >= self._settings.retry_attempts:
                raise failure
            self._logger.debug(
                "openai-compatible retrying path=%s attempt=%d reason=%s",
                path,
                attempt + 1,
                type(failure).__name__,
            )
            await asyncio.sleep(self._settings.retry_base_delay * attempt)
        raise AssertionError("unreachable: the retry loop always returns or raises")

    async def _stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        payload = self._chat_payload(request, stream=True)
        state = _StreamState()
        try:
            async with self._client().stream(
                "POST",
                self._settings.endpoint(CHAT_PATH),
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._raise_for_status(response, CHAT_PATH)
                async for line in response.aiter_lines():
                    chunk = self._stream_chunk(line, state)
                    if chunk is not None:
                        yield chunk
        except httpx.TimeoutException as error:
            raise AITimeoutError("the stream timed out") from error
        except httpx.HTTPError as error:
            raise AITransportError(
                f"the service became unreachable during the stream: {type(error).__name__}"
            ) from error
        # One terminal chunk, whether the service sent its sentinel or simply stopped talking.
        yield ChatChunk(content="", done=True, model=self._settings.model, usage=state.usage)

    def _stream_chunk(self, line: str, state: _StreamState) -> ChatChunk | None:
        text = line.strip()
        if not text or text.startswith(":") or not text.startswith("data:"):
            return None
        payload = text[len("data:") :].strip()
        if not payload:
            return None
        if payload == "[DONE]":
            return None
        data = _decode_object(payload, source=f"a streamed line from {CHAT_PATH}")
        self._raise_for_error_field(data)
        if _as_object(data.get("usage")) is not None:
            state.usage = _usage(data.get("usage"))
        choice = _first_choice(data)
        if choice is None:
            return None
        delta = _as_object(choice.get("delta"))
        content = delta.get("content") if delta is not None else None
        if content is None or content == "":
            return None
        if not isinstance(content, str):
            raise AIInvalidPayloadError("the endpoint streamed a delta that is not a string")
        model = data.get("model")
        return ChatChunk(
            content=content, model=model if isinstance(model, str) and model else self._settings.model
        )

    def _chat_response(self, data: Mapping[str, object]) -> ChatResponse:
        choices = _as_sequence(data.get("choices"))
        if not choices:
            raise AIInvalidPayloadError(f"the {CHAT_PATH} response carries no choices")
        choice = _as_object(choices[0])
        if choice is None:
            raise AIInvalidPayloadError(f"the first {CHAT_PATH} choice is not an object")
        message = _as_object(choice.get("message"))
        if message is None:
            raise AIInvalidPayloadError(f"the {CHAT_PATH} response has no message object")
        content = message.get("content")
        if content is None:
            # A reply that asks for a tool carries no text, which is not a malformed response.
            content = ""
        if not isinstance(content, str):
            raise AIInvalidPayloadError("the assistant content is not a string")
        tool_calls = _tool_calls(message.get("tool_calls"))
        model = data.get("model")
        return ChatResponse(
            message=Message.assistant(content, tool_calls=tool_calls),
            model=model if isinstance(model, str) and model else self._settings.model,
            usage=_usage(data.get("usage")),
            finish_reason=_finish_reason(choice, tool_calls),
        )

    def _embedding_response(
        self, data: Mapping[str, object], *, inputs: int, model: str
    ) -> EmbeddingResponse:
        rows = _as_sequence(data.get("data"))
        if not rows:
            raise AIInvalidPayloadError(f"the {EMBEDDINGS_PATH} response carries no embeddings")
        positioned: list[tuple[int, tuple[float, ...]]] = []
        for position, item in enumerate(rows):
            row = _as_object(item)
            if row is None:
                raise AIInvalidPayloadError("every embedding must be an object")
            index = row.get("index")
            positioned.append(
                (
                    index if isinstance(index, int) and not isinstance(index, bool) else position,
                    _vector(row.get("embedding")),
                )
            )
        # The API may return the vectors in any order; ``index`` is what says which input each one
        # belongs to, and the contract promises the order the inputs were given in.
        positioned.sort(key=lambda item: item[0])
        vectors = [vector for _, vector in positioned]
        if len(vectors) != inputs:
            raise AIInvalidPayloadError(
                f"the endpoint returned {len(vectors)} embedding(s) for {inputs} input(s)"
            )
        returned = data.get("model")
        return EmbeddingResponse(
            model=returned if isinstance(returned, str) and returned else model,
            embeddings=tuple(vectors),
            usage=_usage(data.get("usage")),
        )

    def _chat_payload(self, request: ChatRequest, *, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model or self._settings.model,
            "messages": [_message_payload(message) for message in request.messages],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop:
            payload["stop"] = list(request.stop)
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "xyberos_response",
                    "schema": dict(request.response_schema),
                    "strict": True,
                },
            }
        if request.tools:
            payload["tools"] = [_tool_payload(tool) for tool in request.tools]
        if stream:
            payload["stream"] = True
            # Without this the service reports no usage on a stream, and the contract requires usage
            # to be reported rather than guessed.
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        return headers

    def _raise_for_status(self, response: httpx.Response, path: str) -> None:
        """Map an HTTP failure onto the exception the contract asks for."""
        status = response.status_code
        if status < 400:
            return
        detail = _error_detail(response)
        if status in {401, 403}:
            raise AIConfigurationError(
                f"the endpoint at {self._settings.safe_base_url} rejected the configured api_key "
                f"with {status}: {detail}"
            )
        if status == 429:
            raise AIRateLimitError(
                f"the endpoint rate limited the call to {path} with 429: {detail}"
            )
        if status == 408:
            raise AITimeoutError(f"the endpoint answered 408 for the call to {path}: {detail}")
        if status == 404 and "model" in detail.lower():
            raise AIModelNotFoundError(
                f"the model {self._settings.model!r} is not available on this endpoint ({detail}); "
                "configure another model, because Xyberos never downloads one",
                model=self._settings.model,
            )
        if status == 404:
            raise AIRequestError(
                f"the endpoint answered 404 for {path}: {detail}; check that base_url "
                f"({self._settings.safe_base_url}) names the API root, including any /v1 suffix"
            )
        if status in _RETRYABLE_STATUSES or status >= 500:
            raise AITransportError(f"the endpoint answered {status} for {path}: {detail}")
        raise AIRequestError(f"the endpoint rejected the call to {path} with {status}: {detail}")

    def _raise_for_error_field(self, data: Mapping[str, object]) -> None:
        """Turn a provider-reported error inside a successful response into a normalized error.

        A gateway that cannot serve a request sometimes says so in a body with a 200 beside it, and a
        caller should not have to read prose to find out that the call failed.
        """
        error = data.get("error")
        if error is None:
            return
        text = _error_text(error)
        lowered = text.lower()
        if "model" in lowered and ("not" in lowered or "unknown" in lowered):
            raise AIModelNotFoundError(
                f"the model {self._settings.model!r} is not available on this endpoint ({text}); "
                "configure another model, because Xyberos never downloads one",
                model=self._settings.model,
            )
        if "rate limit" in lowered or "too many requests" in lowered:
            raise AIRateLimitError(f"the endpoint rate limited the request: {text}")
        if any(word in lowered for word in ("unavailable", "timeout", "try again", "overloaded")):
            raise AITransportError(f"the endpoint is temporarily unavailable: {text}")
        raise AIRequestError(f"the endpoint reported an error it cannot retry: {text}")

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            timeout = httpx.Timeout(self._settings.timeout, connect=self._settings.connect_timeout)
            self._http = httpx.AsyncClient(timeout=timeout)
            self._owns_client = True
        return self._http


def openai_compatible_provider(
    settings: OpenAICompatibleSettings,
    *,
    client: httpx.AsyncClient | None = None,
    logger: Logger | None = None,
) -> Callable[[], Awaitable[OpenAICompatibleProvider]]:
    """Return a zero-argument factory suitable for ``App.provide(ModelProvider, ..., eager=True)``."""

    async def factory() -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(settings, client=client, logger=logger)

    return factory


def _message_payload(message: Message) -> dict[str, object]:
    """Translate one contract message into the API's shape.

    A tool result is sent with the tool's name and without a call id: the contract's
    ``Message.tool_result`` names the tool that answered, and carries no call id to point back at.
    """
    payload: dict[str, object] = {"role": message.role.value, "content": message.content}
    if message.role is Role.TOOL and message.tool_name:
        payload["name"] = message.tool_name
    if message.tool_calls:
        payload["tool_calls"] = [_tool_call_payload(call) for call in message.tool_calls]
    return payload


def _tool_call_payload(call: ToolCall) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "function",
        "function": {"name": call.name, "arguments": json.dumps(dict(call.arguments))},
    }
    if call.call_id:
        payload["id"] = call.call_id
    return payload


def _tool_payload(tool: ToolSpec) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.parameters),
        },
    }


def _as_object(value: object) -> Mapping[str, object] | None:
    """Return ``value`` as a string-keyed mapping, or ``None`` when it is not an object.

    Decoded JSON arrives as ``object``, and stating the shape once here is what keeps the rest of
    the module readable by a type checker: a bare ``isinstance(..., Mapping)`` narrows to a mapping
    with unknown keys, and every unknown spreads. Every field below is read through this narrowing
    instead.
    """
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, object], value)


def _as_sequence(value: object) -> Sequence[object] | None:
    """Return ``value`` as an array of elements, or ``None`` when it is not an array.

    A string is a sequence of characters and never what the API sends where an array belongs, so it
    is refused here rather than iterated one character at a time later.
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    return cast(Sequence[object], value)


def _tool_calls(raw: object) -> tuple[ToolCall, ...]:
    if raw is None:
        return ()
    items = _as_sequence(raw)
    if items is None:
        raise AIInvalidPayloadError("tool_calls must be an array")
    calls: list[ToolCall] = []
    for item in items:
        call = _as_object(item)
        if call is None:
            raise AIInvalidPayloadError("every tool call must be an object")
        function = _as_object(call.get("function"))
        if function is None:
            raise AIInvalidPayloadError("every tool call needs a function object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise AIInvalidPayloadError("every tool call needs a function name")
        call_id = call.get("id")
        calls.append(
            ToolCall(
                name=name,
                arguments=_tool_arguments(function.get("arguments"), name),
                call_id=call_id if isinstance(call_id, str) and call_id else None,
            )
        )
    return tuple(calls)


def _tool_arguments(raw: object, name: str) -> dict[str, object]:
    """Read a tool call's arguments, which arrive as a JSON string rather than as an object."""
    if raw is None:
        return {}
    decoded: object = raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except ValueError as error:
            raise AIInvalidPayloadError(
                f"the endpoint returned tool arguments for {name!r} that are not JSON"
            ) from error
    arguments = _as_object(decoded)
    if arguments is None:
        raise AIInvalidPayloadError(f"the arguments of tool {name!r} must be an object")
    return dict(arguments)


def _vector(raw: object) -> tuple[float, ...]:
    values = _as_sequence(raw)
    if not values:
        raise AIInvalidPayloadError("every embedding must be a non-empty array of numbers")
    vector: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AIInvalidPayloadError("the endpoint returned a non-numeric embedding value")
        vector.append(float(value))
    return tuple(vector)


def _usage(raw: object) -> Usage:
    """Read the usage block, treating a missing or unusable one as unknown rather than guessing."""
    values = _as_object(raw)
    if values is None:
        return Usage()
    return Usage(
        input_tokens=_count(values.get("prompt_tokens")),
        output_tokens=_count(values.get("completion_tokens")),
    )


def _finish_reason(
    choice: Mapping[str, object], tool_calls: tuple[ToolCall, ...]
) -> FinishReason | None:
    if tool_calls:
        return FinishReason.TOOL_CALLS
    reason = choice.get("finish_reason")
    if reason is None:
        return None
    if reason == "stop":
        return FinishReason.STOP
    if reason == "length":
        return FinishReason.LENGTH
    if reason in {"tool_calls", "function_call"}:
        return FinishReason.TOOL_CALLS
    if reason == "content_filter":
        # The API's own word for a reply it declined to finish; Xyberos reports it as a refusal
        # rather than inferring one from the text.
        return FinishReason.REFUSAL
    return FinishReason.OTHER


def _first_choice(data: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return the first choice, or ``None`` when the chunk carries none.

    A usage-only chunk legitimately has no choices, which is why this is not an error here.
    """
    choices = _as_sequence(data.get("choices"))
    if not choices:
        return None
    return _as_object(choices[0])


def _model_ids(data: Mapping[str, object]) -> tuple[str, ...]:
    rows = _as_sequence(data.get("data"))
    if rows is None:
        return ()
    identifiers: list[str] = []
    for row in rows:
        entry = _as_object(row)
        if entry is None:
            identifier: object = row
        else:
            identifier = entry.get("id")
        if isinstance(identifier, str) and identifier:
            identifiers.append(identifier)
    return tuple(identifiers)


def _error_detail(response: httpx.Response) -> str:
    """The service's own explanation, when it gave one, short enough for a log line."""
    data = _safe_json(response)
    error = data.get("error")
    if error is not None:
        return _error_text(error)
    text = response.text.strip()
    return text[:200] if text else "no detail"


def _error_text(error: object) -> str:
    """Return the service's own explanation, however it chose to phrase it."""
    entry = _as_object(error)
    if entry is not None:
        message = entry.get("message")
        code = entry.get("code") or entry.get("type")
        if isinstance(message, str) and message:
            return f"{message} ({code})" if isinstance(code, str) and code else message
        return "no message"
    if isinstance(error, str) and error:
        return error
    return "no message"


def _decode_object(text: str, *, source: str) -> dict[str, object]:
    try:
        decoded: object = json.loads(text)
    except ValueError as error:
        raise AIInvalidPayloadError(f"{source} is not JSON: {error}") from error
    data = _as_object(decoded)
    if data is None:
        raise AIInvalidPayloadError(f"{source} is {type(decoded).__name__} instead of an object")
    return dict(data)


def _safe_json(response: httpx.Response) -> dict[str, object]:
    try:
        decoded: object = response.json()
    except ValueError:
        return {}
    data = _as_object(decoded)
    return {} if data is None else dict(data)


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
