"""Run native authorization in staging; failed consent cannot erase old tokens."""
import json
from pathlib import Path
import tempfile


def run_authorization(flow, config):
    from hermes_cli.web_server_mcp import _run_dashboard_mcp_oauth, _mcp_oauth_transaction
    from hermes_cli.mcp_config import _resolve_mcp_server_config, _save_mcp_server
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    from tools.mcp_oauth import HermesTokenStorage, _write_json
    from tools.mcp_oauth_manager import get_manager

    target_home = flow.hermes_home
    target = HermesTokenStorage(flow.server_name, hermes_home=target_home)
    baseline = target.snapshot()
    # Resolve owner-scoped environment references before entering the temporary
    # profile. Commit the original references, never resolved client secrets.
    resolved = _resolve_mcp_server_config(config)
    # The native dashboard extends the outer probe timeout, but the transport's
    # initialize() has its own shorter timeout. Give human consent the same
    # window there; retain the normal configured timeout after connection.
    resolved = {**resolved, "connect_timeout": max(float(resolved.get("connect_timeout", 0) or 0), 330)}
    staging_parent = Path(target_home) / "zoen" / "oauth-pending"
    staging_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with tempfile.TemporaryDirectory(prefix="login-", dir=staging_parent) as staging:
            flow.hermes_home = staging
            try:
                _run_dashboard_mcp_oauth(flow, resolved)
                if flow.snapshot()["status"] != "approved":
                    return
                authorized = HermesTokenStorage(flow.server_name, hermes_home=staging).snapshot()
            finally:
                get_manager().evict(flow.server_name, hermes_home=staging)
                flow.hermes_home = target_home
            # Same native lock as CLI/dashboard reauthorization. A separately
            # refreshed/changed connection wins over this older pending login.
            with _mcp_oauth_transaction(flow):
                if target.snapshot() != baseline:
                    raise RuntimeError("connection_changed_during_login")
                home_token = set_hermes_home_override(target_home)
                try:
                    # Native atomic JSON writer keeps each credential at 0600.
                    # Client/metadata first, token last; readers see a full token.
                    token_name = target._tokens_path().name
                    if token_name not in authorized:
                        raise RuntimeError("authorization_produced_no_token")
                    for name in sorted(authorized, key=lambda name: name == token_name):
                        _write_json(target._tokens_path().parent / name, json.loads(authorized[name]))
                    _save_mcp_server(flow.server_name, config)
                except Exception:
                    target.restore(baseline)
                    raise
                finally:
                    reset_hermes_home_override(home_token)
                get_manager().evict(flow.server_name, hermes_home=target_home)
    except Exception:
        with flow._lock:
            flow.status = "error"
            flow.error = "connection_commit_failed"
            flow.failure_code = flow.error
    finally:
        flow.hermes_home = target_home
