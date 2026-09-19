"""Discover native connector manifests without installing or enabling every tool."""


def availability(entry):
    if entry.install or entry.auth.env or entry.transport.env:
        return "requires_operator_setup"
    if entry.transport.type != "http" or not (entry.transport.url or "").startswith("https://"):
        return "requires_local_application"
    return {"oauth": "requires_provider_authorization", "none": "no_login_required"}.get(
        entry.auth.type, "requires_operator_setup")


def catalog():
    from hermes_cli.mcp_catalog import list_catalog
    return [entry for entry in list_catalog()
            if availability(entry) in {"requires_provider_authorization", "no_login_required"}]


def catalog_result(query=""):
    from hermes_cli.mcp_catalog import list_catalog
    entries = [{"name": entry.name, "description": entry.description, "source": entry.source,
                "auth": entry.auth.type, "availability": availability(entry)} for entry in list_catalog()]
    entries.extend([
        {"name": "google", "description": "Google Gmail, Calendar, Drive, Docs, Sheets and Contacts through Zoen's own OAuth app; permissions are enabled by the operator after Google verification.",
         "auth": "zoen_oauth", "availability": "requires_zoen_google_setup_and_verification"},
        {"name": "slack", "description": "Slack messages and workspaces through the existing Plow connection.",
         "auth": "plow", "availability": "requires_plow_connector_access"},
    ])
    terms = str(query or "").casefold().split()
    matches = [entry for entry in entries if all(term in (entry["name"] + " " + entry["description"]).casefold() for term in terms)]
    return {"ok": True, "total": len(entries), "connectors": matches,
            "instruction": "Activate only services relevant to the owner's request. Catalog presence is not verified account access. Operator/local entries cannot connect through this tool."}


def server_config(name):
    from hermes_cli.mcp_catalog import _build_server_config
    from hermes_cli.mcp_config import _get_mcp_servers
    entry = next((entry for entry in catalog() if entry.name == name), None)
    if entry is None:
        raise ValueError("connector_not_in_remote_catalog")
    cfg = _build_server_config(entry, None)
    prior = _get_mcp_servers().get(name, {})
    if prior and (prior.get("url") != cfg["url"] or (prior.get("auth") or "none") != entry.auth.type
                  or prior.get("headers") or prior.get("command")):
        raise ValueError("existing_connector_configuration_conflicts")
    cfg.update(prior)
    cfg["enabled"] = True
    if "tools" not in cfg:
        selection = {}
        if entry.tools.default_enabled is not None:
            selection["include"] = list(entry.tools.default_enabled)
        if entry.tools.default_excluded:
            selection["exclude"] = list(entry.tools.default_excluded)
        if selection:
            cfg["tools"] = selection
    if cfg.get("auth") == "oauth" and (cfg.get("oauth") or {}).get("flow", "browser") != "browser":
        raise ValueError("device_flow_not_available_in_imessage")
    return cfg
