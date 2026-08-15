"""Example (M2): point the HTTP/API connector at Open-Meteo and call a typed tool.

Requires network access (Open-Meteo is free, no API key). Run from this folder:

    python examples/http_api_weather.py

If the plugin is installed (``pip install -e .``) it can be run from anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos import create_app

from xyberos_http_api import HttpApiPlugin


def main() -> None:
    spec_path = Path(__file__).resolve().parent / "weather.json"
    app = create_app()
    app.load_plugin(HttpApiPlugin(spec_path))

    print("registered tools:", app.tools.names)
    print()
    print("get_forecast(latitude=40.71, longitude=-74.01) →")
    forecast = app.tools.execute("get_forecast", None, latitude=40.71, longitude=-74.01)
    print(" ", forecast.get("current_weather"))

    app.unload_plugin("http_api")


if __name__ == "__main__":
    main()
