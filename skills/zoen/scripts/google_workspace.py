#!/usr/bin/env python3
"""Run Hermes' bundled Google API commands with Zoen's independent OAuth account."""
import importlib.util
import json
from pathlib import Path
import sys

from google_account import Account, GoogleError, verify_identity


def get_credentials():
    from google.auth.credentials import Credentials

    class ZoenCredentials(Credentials):
        def refresh(self, request):
            self.token = Account().token(force=True)

    credentials = ZoenCredentials()
    credentials.token = Account().token()
    return credentials


def main():
    if sys.argv[1:] == ["identity"]:
        print(json.dumps(verify_identity(Account().token())))
        return
    source = Path("/opt/hermes/skills/productivity/google-workspace/scripts/google_api.py")
    if not source.is_file():
        raise GoogleError("bundled_google_api_unavailable")
    spec = importlib.util.spec_from_file_location("zoen_native_google_api", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Reuse the installed command implementations. Never invoke its legacy
    # localhost OAuth setup or let gws load a different Google account.
    module.get_credentials = get_credentials
    module._gws_binary = lambda: None
    module.main()


if __name__ == "__main__":
    try:
        main()
    except GoogleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
