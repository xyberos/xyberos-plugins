"""What this provider promises without a network, and the suite it runs against a real stub server.

The tests are ordinary pytest tests: an async scenario is a synchronous test that calls
``asyncio.run(...)``. The error-mapping, capability, and wire-format tests drive the adapter through
``httpx.MockTransport``, which needs no socket. The conformance test starts the stub server this
package ships — a real ``ThreadingHTTPServer`` — so the shipped suite runs over HTTP rather than over
a mock of it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from xyberos.ai import (
    ChatChunk,
    ChatRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    FinishReason,
    Message,
    ModelCapabilities,
    ModelHealth,
    ModelStatus,
    ToolCall,
    ToolSpec,
    Usage,
)
from xyberos.ai.testing import (
    assert_embedding_provider_contract,
    assert_model_provider_contract,
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

# The stub server's routes are the absolute paths a base URL of ``.../v1`` produces, which is what a
# recorded request reports; the provider's own constants are the suffixes joined onto that base.
from xyberos_openai_compatible.stub import (
    CHAT_MODEL,
    CHAT_PATH,
    EMBEDDING_MODEL,
    EMBEDDING_WIDTH,
    MODELS_PATH,
    running_stub,
    vector_for,
)
from xyberos_openai_compatible import (
    OpenAICompatibleProvider,
    OpenAICompatibleSettings,
    openai_compatible_provider,
)
from xyberos_openai_compatible.conformance import settings_from_environment
from xyberos_openai_compatible.provider import (
    CHAT_PATH as CHAT_SUFFIX,
)
from xyberos_openai_compatible.provider import (
    EMBEDDINGS_PATH as EMBEDDINGS_SUFFIX,
)
from xyberos_openai_compatible.provider import (
    MODELS_PATH as MODELS_SUFFIX,
)

WEATHER_SPEC = ToolSpec(
    name="weather",
    description="look up weather",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)
CITY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"city": {"type": "string"}},
    "required": ["city"],
}


class Routes:
    """A scripted set of HTTP routes that records every request it receives."""

    def __init__(
        self, routes: dict[str, httpx.Response | Callable[[httpx.Request], httpx.Response]]
    ) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"error": {"message": "unknown path"}})
        if callable(route):
            return route(request)
        return route

    def payload_for(self, path: str) -> dict[str, object]:
        for request in self.requests:
            if request.url.path == path:
                return json.loads(request.content)
        raise AssertionError(f"no request was made to {path}")


def settings(**overrides: object) -> OpenAICompatibleSettings:
    values: dict[str, object] = {
        "model": "gpt-4o-mini",
        "base_url": "http://stub.test/v1",
        "api_key": "sk-test",
    }
    values.update(overrides)
    return OpenAICompatibleSettings(**values)  # type: ignore[arg-type]


def make_provider(routes: Routes, **overrides: object) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(routes))
    return OpenAICompatibleProvider(settings(**overrides), client=client)


def _chat_body(content: str = "ok") -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


def _sse(lines: list[dict[str, object]]) -> str:
    body = "".join(f"data: {json.dumps(line)}\n\n" for line in lines)
    return f"{body}data: [DONE]\n\n"


def test_settings_require_an_explicit_model() -> None:
    with pytest.raises(AIConfigurationError, match="never chooses a model"):
        OpenAICompatibleSettings(model="")
    with pytest.raises(AIConfigurationError, match="never chooses a model"):
        OpenAICompatibleSettings(model="   ")


def test_settings_validate_the_base_url_and_never_accept_credentials() -> None:
    assert OpenAICompatibleSettings(model="m", base_url="http://127.0.0.1:59080/v1/").base_url == (
        "http://127.0.0.1:59080/v1"
    )
    with pytest.raises(AIConfigurationError, match="must be an http"):
        OpenAICompatibleSettings(model="m", base_url="gateway.test/v1")
    with pytest.raises(AIConfigurationError, match="must not embed credentials"):
        OpenAICompatibleSettings(model="m", base_url="https://sk-secret@gateway.test/v1")
    with pytest.raises(AIConfigurationError, match="must be a non-empty URL"):
        OpenAICompatibleSettings(model="m", base_url="   ")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"timeout": 0}, "timeout must be greater than zero"),
        ({"connect_timeout": -1.0}, "connect_timeout must be greater than zero"),
        ({"retry_attempts": 0}, "retry_attempts must be at least 1"),
        ({"retry_base_delay": -0.1}, "retry_base_delay must not be negative"),
        ({"embedding_model": "  "}, "embedding_model must be a non-empty model name"),
        ({"tools": "yes"}, "tools must be true or false"),
        ({"embeddings": 1}, "embeddings must be true or false"),
    ],
)
def test_settings_refuse_a_value_that_would_fail_later(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(AIConfigurationError, match=message):
        OpenAICompatibleSettings(model="m", **changes)  # type: ignore[arg-type]


def test_capabilities_are_exactly_what_the_settings_claim() -> None:
    claims = settings(
        tools=True, structured_output=True, streaming=False, embeddings=True
    ).capabilities

    assert claims == ModelCapabilities(
        tools=True, structured_output=True, streaming=False, embeddings=True
    )


def test_the_api_key_is_never_rendered() -> None:
    """A dataclass repr is the quickest way for a credential to reach a log."""
    configured = settings(api_key="sk-s3cret")

    assert "sk-s3cret" not in repr(configured)
    assert "sk-s3cret" not in configured.safe_base_url


def test_a_token_in_the_query_string_is_masked_in_the_safe_url() -> None:
    configured = OpenAICompatibleSettings(
        model="m", base_url="https://gateway.test/v1?api_key=s3cret&team=core"
    )

    assert configured.safe_base_url == "https://gateway.test/v1?api_key=***&team=***"
    assert "s3cret" not in configured.safe_base_url
    assert "core" not in configured.safe_base_url


def test_endpoints_join_a_base_url_with_or_without_a_trailing_slash() -> None:
    without = OpenAICompatibleSettings(model="m", base_url="http://gateway.test:1234/v1")
    with_slash = OpenAICompatibleSettings(model="m", base_url="http://gateway.test:1234/v1/")

    assert without.endpoint(CHAT_SUFFIX) == "http://gateway.test:1234/v1/chat/completions"
    assert with_slash.endpoint(CHAT_SUFFIX) == "http://gateway.test:1234/v1/chat/completions"
    assert without.endpoint(EMBEDDINGS_SUFFIX) == "http://gateway.test:1234/v1/embeddings"
    assert without.endpoint(MODELS_SUFFIX) == "http://gateway.test:1234/v1/models"
    assert "//" not in without.endpoint(CHAT_SUFFIX).removeprefix("http://")
    with pytest.raises(AIConfigurationError, match="non-empty string"):
        without.endpoint("")


def test_a_call_reaches_the_joined_url_and_bears_the_key() -> None:
    routes = Routes({CHAT_PATH: httpx.Response(200, json=_chat_body("hello"))})

    async def scenario() -> str:
        provider = make_provider(routes)
        response = await provider.chat(
            ChatRequest(
                messages=(Message.system("be brief"), Message.user("hello")),
                temperature=0.25,
                max_tokens=64,
                stop=("\n",),
            )
        )
        return response.message.content

    assert asyncio.run(scenario()) == "hello"
    assert str(routes.requests[0].url) == "http://stub.test/v1/chat/completions"
    assert routes.requests[0].headers["authorization"] == "Bearer sk-test"
    payload = routes.payload_for(CHAT_PATH)
    assert payload["model"] == "gpt-4o-mini"
    assert payload["temperature"] == 0.25
    assert payload["max_tokens"] == 64
    assert payload["stop"] == ["\n"]
    assert payload["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"},
    ]
    assert "stream" not in payload


def test_a_structured_request_declares_the_schema_it_expects() -> None:
    routes = Routes({CHAT_PATH: httpx.Response(200, json=_chat_body('{"city":"Paris"}'))})

    async def scenario() -> None:
        provider = make_provider(routes, structured_output=True)
        await provider.chat(
            ChatRequest(messages=(Message.user("where?"),), response_schema=CITY_SCHEMA)
        )

    asyncio.run(scenario())
    assert routes.payload_for(CHAT_PATH)["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "xyberos_response", "schema": CITY_SCHEMA, "strict": True},
    }


def test_a_tool_call_comes_back_in_the_contract_shape() -> None:
    body = _chat_body("")
    body["choices"][0]["message"] = {  # type: ignore[index]
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "weather", "arguments": '{"city": "Paris"}'},
            }
        ],
    }
    body["choices"][0]["finish_reason"] = "tool_calls"  # type: ignore[index]
    routes = Routes({CHAT_PATH: httpx.Response(200, json=body)})

    async def scenario() -> tuple[FinishReason | None, tuple[ToolCall, ...]]:
        provider = make_provider(routes, tools=True)
        response = await provider.chat(
            ChatRequest(messages=(Message.user("weather?"),), tools=(WEATHER_SPEC,))
        )
        return response.finish_reason, response.message.tool_calls

    finish_reason, calls = asyncio.run(scenario())
    assert finish_reason is FinishReason.TOOL_CALLS
    assert calls == (ToolCall(name="weather", arguments={"city": "Paris"}, call_id="call_1"),)
    assert routes.payload_for(CHAT_PATH)["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "look up weather",
                "parameters": dict(WEATHER_SPEC.parameters),
            },
        }
    ]


def test_a_stream_reports_content_and_one_terminal_chunk_that_carries_usage() -> None:
    lines: list[dict[str, object]] = [
        {
            "id": "chatcmpl-1",
            "model": "gpt-4o-mini",
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": "He"}, "finish_reason": None}
            ],
        },
        {
            "id": "chatcmpl-1",
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {"content": "llo"}, "finish_reason": None}],
        },
        {
            "id": "chatcmpl-1",
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        {
            "id": "chatcmpl-1",
            "model": "gpt-4o-mini",
            "choices": [],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
    ]
    routes = Routes(
        {CHAT_PATH: httpx.Response(200, text=_sse(lines), headers={"Content-Type": "text/event-stream"})}
    )

    async def scenario() -> tuple[ChatChunk, ...]:
        provider = make_provider(routes)
        request = ChatRequest(messages=(Message.user("hi"),))
        return tuple([chunk async for chunk in provider.stream(request)])

    chunks = asyncio.run(scenario())
    assert "".join(chunk.content for chunk in chunks if not chunk.done) == "Hello"
    terminals = [chunk for chunk in chunks if chunk.done]
    assert len(terminals) == 1
    assert terminals[0].usage == Usage(input_tokens=3, output_tokens=2)
    assert routes.payload_for(CHAT_PATH)["stream"] is True
    assert routes.payload_for(CHAT_PATH)["stream_options"] == {"include_usage": True}


def test_a_stream_that_stops_without_a_sentinel_still_ends_once() -> None:
    body = _sse(
        [
            {
                "id": "chatcmpl-1",
                "model": "gpt-4o-mini",
                "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
            }
        ]
    ).replace("data: [DONE]\n\n", "")
    routes = Routes(
        {CHAT_PATH: httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})}
    )

    async def scenario() -> tuple[ChatChunk, ...]:
        provider = make_provider(routes)
        request = ChatRequest(messages=(Message.user("hi"),))
        return tuple([chunk async for chunk in provider.stream(request)])

    chunks = asyncio.run(scenario())
    assert [chunk.done for chunk in chunks] == [False, True]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, AIRequestError),
        (401, AIConfigurationError),
        (403, AIConfigurationError),
        (408, AITimeoutError),
        (409, AITransportError),
        (429, AIRateLimitError),
        (500, AITransportError),
        (503, AITransportError),
    ],
)
def test_a_failed_call_maps_onto_the_contract_exception(
    status: int, expected: type[BaseException]
) -> None:
    routes = Routes({CHAT_PATH: httpx.Response(status, json={"error": {"message": "no"}})})

    async def scenario() -> None:
        provider = make_provider(routes, retry_attempts=1)
        with pytest.raises(expected) as caught:
            await provider.chat(ChatRequest(messages=(Message.user("hello"),)))
        assert type(caught.value) is expected
        assert str(status) in str(caught.value)

    asyncio.run(scenario())


def test_a_missing_model_is_reported_as_a_missing_model() -> None:
    routes = Routes(
        {
            CHAT_PATH: httpx.Response(
                404,
                json={
                    "error": {
                        "message": "The model `gpt-nope` does not exist",
                        "code": "model_not_found",
                    }
                },
            )
        }
    )

    async def scenario() -> None:
        provider = make_provider(routes, model="gpt-nope", retry_attempts=1)
        with pytest.raises(AIModelNotFoundError) as caught:
            await provider.chat(ChatRequest(messages=(Message.user("hello"),)))
        assert caught.value.model == "gpt-nope"

    asyncio.run(scenario())


def test_a_404_for_a_wrong_base_url_names_the_base_url() -> None:
    routes = Routes({CHAT_PATH: httpx.Response(404, json={"error": {"message": "Not Found"}})})

    async def scenario() -> None:
        provider = make_provider(routes, retry_attempts=1)
        with pytest.raises(AIRequestError, match="check that base_url"):
            await provider.chat(ChatRequest(messages=(Message.user("hello"),)))

    asyncio.run(scenario())


def test_an_unreachable_endpoint_is_a_transport_error_and_a_slow_one_is_a_timeout() -> None:
    def refusing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    async def scenario() -> None:
        with pytest.raises(AITransportError, match="unreachable") as refused:
            await make_provider(Routes({CHAT_PATH: refusing}), retry_attempts=1).chat(
                ChatRequest(messages=(Message.user("hello"),))
            )
        assert type(refused.value) is AITransportError
        with pytest.raises(AITimeoutError, match="timed out"):
            await make_provider(Routes({CHAT_PATH: slow}), retry_attempts=1).chat(
                ChatRequest(messages=(Message.user("hello"),))
            )

    asyncio.run(scenario())


def test_a_response_that_is_not_an_object_is_an_invalid_payload() -> None:
    routes = Routes({CHAT_PATH: httpx.Response(200, text="[]")})

    async def scenario() -> None:
        provider = make_provider(routes, retry_attempts=1)
        with pytest.raises(AIInvalidPayloadError, match="instead of an object"):
            await provider.chat(ChatRequest(messages=(Message.user("hello"),)))

    asyncio.run(scenario())


def test_a_transient_failure_is_retried_within_the_configured_budget() -> None:
    attempts = {"count": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, json={"error": {"message": "try again"}})
        return httpx.Response(200, json=_chat_body("recovered"))

    async def scenario() -> str:
        provider = make_provider(Routes({CHAT_PATH: flaky}), retry_attempts=2)
        response = await provider.chat(ChatRequest(messages=(Message.user("hello"),)))
        return response.message.content

    assert asyncio.run(scenario()) == "recovered"
    assert attempts["count"] == 2


def test_a_rejected_request_is_not_retried() -> None:
    attempts = {"count": 0}

    def rejected(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"error": {"message": "invalid temperature"}})

    async def scenario() -> None:
        provider = make_provider(Routes({CHAT_PATH: rejected}), retry_attempts=3)
        with pytest.raises(AIRequestError):
            await provider.chat(ChatRequest(messages=(Message.user("hello"),)))

    asyncio.run(scenario())
    assert attempts["count"] == 1


def test_a_capability_that_is_not_claimed_is_refused_rather_than_attempted() -> None:
    routes = Routes({})

    async def scenario() -> None:
        provider = make_provider(routes, streaming=False)
        with pytest.raises(AIUnsupportedCapabilityError) as refused:
            await provider.chat(
                ChatRequest(messages=(Message.user("hi"),), tools=(WEATHER_SPEC,))
            )
        assert refused.value.capability == "tools"

        with pytest.raises(AIUnsupportedCapabilityError) as refused:
            await provider.chat(
                ChatRequest(messages=(Message.user("hi"),), response_schema=CITY_SCHEMA)
            )
        assert refused.value.capability == "structured_output"

        with pytest.raises(AIUnsupportedCapabilityError) as refused:
            provider.stream(ChatRequest(messages=(Message.user("hi"),)))
        assert refused.value.capability == "streaming"

        with pytest.raises(AIUnsupportedCapabilityError) as refused:
            await provider.embed(EmbeddingRequest(inputs=("hi",)))
        assert refused.value.capability == "embeddings"

    asyncio.run(scenario())
    assert routes.requests == [], "a refused capability is never sent"


def test_an_embeddings_only_configuration_refuses_chat() -> None:
    routes = Routes({})

    async def scenario() -> None:
        provider = make_provider(routes, chat=False)
        with pytest.raises(AIUnsupportedCapabilityError) as refused:
            await provider.chat(ChatRequest(messages=(Message.user("hi"),)))
        assert refused.value.capability == "chat"

    asyncio.run(scenario())
    assert routes.requests == []


def test_an_embedding_call_without_a_model_names_the_setting_to_set() -> None:
    routes = Routes({})

    async def scenario() -> None:
        provider = make_provider(routes, embeddings=True)
        with pytest.raises(AIConfigurationError, match="no embedding model is configured"):
            await provider.embed(EmbeddingRequest(inputs=("hi",)))

    asyncio.run(scenario())


def test_health_distinguishes_unreachable_unhealthy_and_missing_model() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async def scenario() -> tuple[ModelHealth, ...]:
        refused = await make_provider(Routes({MODELS_PATH: unreachable})).health()
        rejected = await make_provider(
            Routes({MODELS_PATH: httpx.Response(401, json={"error": {"message": "bad key"}})})
        ).health()
        listing = await make_provider(
            Routes(
                {
                    MODELS_PATH: httpx.Response(
                        200, json={"object": "list", "data": [{"id": "other-model"}]}
                    )
                }
            )
        ).health()
        ready = await make_provider(
            Routes(
                {
                    MODELS_PATH: httpx.Response(
                        200,
                        json={"object": "list", "data": [{"id": "gpt-4o-mini"}]},
                        headers={"openai-version": "2020-10-01"},
                    )
                }
            )
        ).health()
        return refused, rejected, listing, ready

    refused, rejected, listing, ready = asyncio.run(scenario())
    assert refused.status is ModelStatus.UNREACHABLE
    assert rejected.status is ModelStatus.UNHEALTHY
    assert "api_key" in rejected.detail
    assert listing.status is ModelStatus.MODEL_UNAVAILABLE
    assert "other-model" in listing.detail
    assert ready.status is ModelStatus.READY
    assert ready.ready
    assert ready.provider_version == "2020-10-01"
    assert refused.model == "gpt-4o-mini"
    assert "sk-test" not in refused.detail


def test_the_provider_factory_is_zero_argument_and_needs_no_network() -> None:
    factory = openai_compatible_provider(settings())

    assert factory.__code__.co_argcount == 0

    async def scenario() -> OpenAICompatibleProvider:
        return await factory()

    provider = asyncio.run(scenario())
    assert provider.name == "openai-compatible"
    assert provider.model == "gpt-4o-mini"
    assert provider.settings.model == "gpt-4o-mini"


def test_the_conformance_module_reads_the_environment_it_documents() -> None:
    defaults = settings_from_environment({})

    assert defaults.base_url == "http://127.0.0.1:59080/v1"
    assert defaults.api_key == ""
    assert defaults.model == "stub-model"
    assert defaults.embeddings is True
    assert defaults.embedding_model == EMBEDDING_MODEL

    configured = settings_from_environment(
        {
            "XYBEROS_OPENAI_BASE_URL": "https://gateway.test/v1/",
            "XYBEROS_OPENAI_API_KEY": "sk-env",
            "XYBEROS_OPENAI_MODEL": "llama-3.3-70b",
            "XYBEROS_OPENAI_TOOLS": "false",
            "XYBEROS_OPENAI_EMBEDDINGS": "no",
        }
    )
    assert configured.base_url == "https://gateway.test/v1"
    assert configured.api_key == "sk-env"
    assert configured.model == "llama-3.3-70b"
    assert configured.tools is False
    assert configured.embeddings is False


def test_the_package_ships_its_types() -> None:
    marker = Path(__file__).resolve().parents[1] / "xyberos_openai_compatible" / "py.typed"

    assert marker.is_file(), "strict-mode consumers need the PEP 561 marker"


def test_the_shipped_suites_pass_against_the_stub_server() -> None:
    """The acceptance criterion: the core's own suite, over real HTTP, against a local service."""
    with running_stub() as stub:
        configured = OpenAICompatibleSettings(
            model=CHAT_MODEL,
            base_url=stub.base_url,
            embedding_model=EMBEDDING_MODEL,
            tools=True,
            structured_output=True,
            embeddings=True,
        )

        async def scenario() -> tuple[str, ...]:
            provider = OpenAICompatibleProvider(configured)
            try:
                checked = list(await assert_model_provider_contract(provider))
                checked.extend(await assert_embedding_provider_contract(provider))
                return tuple(checked)
            finally:
                await provider.aclose()

        checked = asyncio.run(scenario())

    for expectation in (
        "health() reports a ready provider",
        "name and capabilities are declared",
        "chat() returns an assistant message with a model and a finish reason",
        "usage is reported and adds up",
        "stream() yields content and exactly one terminal chunk",
        "structured output honours the requested schema",
        "a tool-calling request is accepted and every call names a declared tool",
        "embed() returns one vector per input, all of one non-zero width",
    ):
        assert expectation in checked, f"the suite did not report: {expectation}"


def test_embeddings_come_back_in_the_order_the_inputs_were_given() -> None:
    with running_stub() as stub:
        configured = OpenAICompatibleSettings(
            model=CHAT_MODEL,
            base_url=stub.base_url,
            embedding_model=EMBEDDING_MODEL,
            embeddings=True,
        )

        async def scenario() -> EmbeddingResponse:
            provider = OpenAICompatibleProvider(configured)
            try:
                return await provider.embed(EmbeddingRequest(inputs=("first", "second, longer")))
            finally:
                await provider.aclose()

        response = asyncio.run(scenario())

    assert response.model == EMBEDDING_MODEL
    assert response.embeddings == (vector_for("first"), vector_for("second, longer"))
    assert response.dimensions == EMBEDDING_WIDTH
    assert response.usage.input_tokens == 3


def test_a_streaming_call_against_the_stub_ends_exactly_once() -> None:
    with running_stub() as stub:
        configured = OpenAICompatibleSettings(model=CHAT_MODEL, base_url=stub.base_url)

        async def scenario() -> tuple[ChatChunk, ...]:
            provider = OpenAICompatibleProvider(configured)
            try:
                request = ChatRequest(messages=(Message.user("say ok"),))
                return tuple([chunk async for chunk in provider.stream(request)])
            finally:
                await provider.aclose()

        chunks = asyncio.run(scenario())

    assert "".join(chunk.content for chunk in chunks if not chunk.done) == "ok"
    terminals = [chunk for chunk in chunks if chunk.done]
    assert len(terminals) == 1
    assert terminals[0].usage is not None
    assert terminals[0].usage.total_tokens >= 1


def test_a_structured_call_against_the_stub_matches_the_schema() -> None:
    with running_stub() as stub:
        configured = OpenAICompatibleSettings(
            model=CHAT_MODEL, base_url=stub.base_url, structured_output=True
        )

        async def scenario() -> str:
            provider = OpenAICompatibleProvider(configured)
            try:
                request = ChatRequest(
                    messages=(Message.user("name a city"),), response_schema=CITY_SCHEMA
                )
                response = await provider.chat(request)
                return response.message.content
            finally:
                await provider.aclose()

        content = asyncio.run(scenario())

    assert json.loads(content) == {"city": "stub"}
