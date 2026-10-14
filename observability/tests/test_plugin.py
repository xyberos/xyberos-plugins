"""The same configuration through the plugin contract: a section, a provider, and a stop hook."""

from __future__ import annotations

import asyncio
import logging

import pytest

from xyberos import App
from xyberos.errors import ConfigurationError, PluginConfigurationError

from xyberos_observability import Observability, ObservabilityPlugin, ObservabilitySettings


def test_the_plugin_declares_the_settings_as_its_config_type() -> None:
    plugin = ObservabilityPlugin()

    assert plugin.name == "observability"
    assert plugin.api_version == "1"
    assert plugin.requires == ()
    assert plugin.config_type is ObservabilitySettings, "the runtime builds the settings from this"
    assert plugin.observability is None, "nothing is configured until the plugin registers"


def test_a_mistyped_plugin_setting_is_refused_by_name() -> None:
    with pytest.raises(PluginConfigurationError, match="levl"):
        App().add_plugin(ObservabilityPlugin(), config={"levl": "DEBUG"})


def test_a_refused_plugin_setting_is_reported_as_a_configuration_error() -> None:
    """The settings refuse a bad value whichever door it arrives through."""
    with pytest.raises(ConfigurationError, match="is not a logging level"):
        App().add_plugin(ObservabilityPlugin(), config={"level": "loud"})


def test_registering_the_plugin_configures_logging_and_provides_the_object() -> None:
    app = App()
    root = logging.getLogger()
    before = tuple(root.handlers)
    previous_level = root.level
    app.add_plugin(ObservabilityPlugin(), config={"level": "DEBUG", "service": "checkout"})

    async def scenario() -> None:
        await app.start()
        try:
            observability = await app.resolve(Observability)
            assert observability.settings.service == "checkout"
            assert len(root.handlers) == len(before) + 1
            assert root.level == logging.DEBUG
        finally:
            await app.stop()

    asyncio.run(scenario())

    assert tuple(root.handlers) == before, "the handler is removed when the application stops"
    assert root.level == previous_level


def test_the_plugin_reports_nothing_to_shut_down_before_it_registers() -> None:
    plugin = ObservabilityPlugin()

    asyncio.run(plugin.stop())

    assert plugin.observability is None
