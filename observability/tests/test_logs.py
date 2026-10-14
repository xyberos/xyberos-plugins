"""The one call: what it installs, what it refuses, and that it still redacts.

The tests are ordinary pytest tests: an async scenario is a synchronous test that calls
``asyncio.run(...)``. Everything here runs offline — no collector, no network, no other process.
"""

from __future__ import annotations

import asyncio
import io
import logging

import pytest

from xyberos import bind_correlation_id
from xyberos.ai import AIFacade, ChatRequest, FakeModelProvider, LoggingPolicy, Message, ModelReply
from xyberos.errors import ConfigurationError

from xyberos_observability import DEFAULT_FORMAT, ObservabilitySettings, configure_logging

#: A value the runtime is told to treat as a secret by ``LoggingPolicy(redact=(...))``.
SECRET = "sk-live-0123456789"


def test_the_one_call_installs_a_handler_a_level_a_format_and_the_context_filter() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("tests.orders")
    previous_level = logger.level

    setup = configure_logging(
        ObservabilitySettings(level="DEBUG", format=DEFAULT_FORMAT, logger="tests.orders"),
        stream=stream,
    )
    try:
        assert setup.handler in logger.handlers
        assert logger.level == logging.DEBUG
        assert [type(attached).__name__ for attached in setup.handler.filters] == [
            "ContextLogFilter"
        ]
        with bind_correlation_id("req-7"):
            logger.info("looked up order 7")
    finally:
        setup.shutdown()

    assert stream.getvalue() == (
        "INFO tests.orders looked up order 7 {'correlation_id': 'req-7'}\n"
    )
    assert logger.level == previous_level


def test_the_setup_takes_it_back_and_shutting_down_twice_is_harmless() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("tests.shutdown")
    previous_level = logger.level
    setup = configure_logging(
        ObservabilitySettings(level="ERROR", logger="tests.shutdown"), stream=stream
    )

    setup.shutdown()
    setup.shutdown()

    assert setup.handler not in logger.handlers
    assert logger.level == previous_level
    logger.warning("after shutdown")
    assert stream.getvalue() == "", "a detached handler must not still be writing"


def test_a_level_someone_else_chose_afterwards_is_left_alone() -> None:
    logger = logging.getLogger("tests.afterwards")
    previous_level = logger.level
    setup = configure_logging(
        ObservabilitySettings(level="DEBUG", logger="tests.afterwards"), stream=io.StringIO()
    )

    try:
        logger.setLevel(logging.CRITICAL)
        setup.shutdown()
        assert logger.level == logging.CRITICAL, "the deployment's later choice wins"
    finally:
        logger.setLevel(previous_level)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"level": "loud"}, "is not a logging level"),
        ({"level": "INFO "}, "is not a logging level"),
        ({"service": "   "}, "service must name the deployment"),
        ({"format": ""}, "format must not be empty"),
        ({"format": "%(nope)s %(message)s"}, "cannot be rendered against a log record"),
        ({"logger": "xyberos ai"}, "must be a dotted identifier"),
        ({"logger": "xyberos "}, "must not have surrounding whitespace"),
    ],
)
def test_settings_refuse_a_value_that_would_fail_later(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        ObservabilitySettings(**changes)  # type: ignore[arg-type]


def test_the_level_may_be_named_or_numbered() -> None:
    assert ObservabilitySettings(level="debug").level_number == logging.DEBUG
    assert ObservabilitySettings(level="30").level_number == logging.WARNING


def test_a_handler_configured_here_still_redacts_a_field_the_runtime_calls_a_secret() -> None:
    """The evidence the plan asks for: the runtime's redaction survives this package's handler.

    The same handler renders the same prompt twice. With nothing declared as a secret, the captured
    content — and the credential inside it — reaches the sink, which is what makes the second half
    evidence rather than a coincidence: the secret is absent there because the runtime classified it
    as one and replaced it before the record was emitted, not because a handler this package
    installs happens to drop content, truncate it away, or reformat the record's arguments.
    """
    stream = io.StringIO()
    setup = configure_logging(
        ObservabilitySettings(level="DEBUG", logger="xyberos.ai"), stream=stream
    )
    prompt = f"token {SECRET} rain?"

    async def scenario(policy: LoggingPolicy) -> None:
        facade = AIFacade(FakeModelProvider([ModelReply.ok("done")]), logging_policy=policy)
        await facade.chat(ChatRequest(messages=(Message.user(prompt),)))

    try:
        asyncio.run(scenario(LoggingPolicy.capturing()))
        assert SECRET in stream.getvalue(), "the handler does render captured content"
        stream.seek(0)
        stream.truncate()
        asyncio.run(scenario(LoggingPolicy.capturing(redact=(SECRET,))))
    finally:
        setup.shutdown()

    rendered = stream.getvalue()
    assert "ai prompt role=user" in rendered
    assert "[redacted]" in rendered
    assert SECRET not in rendered
