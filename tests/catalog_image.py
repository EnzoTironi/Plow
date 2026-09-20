"""Verify the model-facing tool catalog from the image's real seeded config."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, "/opt/hermes")

with tempfile.TemporaryDirectory() as task_home:
    os.environ["HERMES_HOME"] = task_home
    os.environ["HERMES_GATEWAY_SESSION"] = "1"
    # Required for platform registration; this container has no external network.
    os.environ["PLOW_AGENT_TOKEN"] = "local-test-fixture"
    os.environ["PLOW_HOME_CHANNEL"] = "cht_test"
    os.environ["PLOW_API_BASE"] = "http://127.0.0.1:1"
    config_path = Path(task_home) / "config.yaml"
    shutil.copy("/opt/hermes/plow-seed/config.yaml", config_path)
    config = yaml.safe_load(config_path.read_text())
    from hermes_cli.plugins import get_plugin_manager
    from hermes_cli.tools_config import _get_platform_tools
    get_plugin_manager().discover_and_load()
    from gateway.platform_registry import platform_registry
    # Match the gateway's deferred-platform materialization before assembly.
    platform_registry.get("plow-chat")
    assert platform_registry.get("plow_chat") is not None
    loaded = get_plugin_manager()._plugins["plow-chat-platform"]
    assert getattr(loaded.module.PlowChatAdapter, "_zoen_presence", False), "first inbound lacks reception"
    soul = Path("/opt/hermes/plow-seed/SOUL.md").read_text()
    assert soul.lstrip().startswith("# Zoen"), soul[:80]
    assert "You are a Plow assistant" not in soul
    prompt = loaded.module._with_identity("continue", "Spruce", {"lines": []})
    assert prompt.startswith("You are Zoen"), prompt[:120]
    assert "You are Spruce" not in prompt
    selected = _get_platform_tools(config, "plow_chat")
    # Check actual session selection, not an invented all-tools catalog.
    assert {"kanban", "zoen"} <= selected, selected
    from model_tools import get_tool_definitions
    definitions = get_tool_definitions(enabled_toolsets=sorted(selected),
        disabled_toolsets=config["agent"]["disabled_toolsets"],
        quiet_mode=True, skip_tool_search_assembly=True)
    names = {item["function"]["name"] for item in definitions}
    required = {"zoen_connections", "plow_send_sequence", "browser_navigate", "kanban_create", "kanban_list", "cronjob_manage", "terminal"}
    assert not required - names, sorted(required - names)
    print(json.dumps({"model_catalog": sorted(required)}))
