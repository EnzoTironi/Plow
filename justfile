# Zoen checks. `just test` needs only uv; the image recipes need Docker.

# Unit suite: offline, hermetic (tests/conftest.py blocks the network).
test:
    env -u AGENT_ID -u BOSS_ID PYTHONDONTWRITEBYTECODE=1 uv run -q --no-project --python 3.12 \
        --with pytest --with pyyaml --with aiohttp python -m pytest -q -p no:cacheprovider

# The OAuth/WhatsApp relay (Cloudflare Worker), Node 24.
relay-test:
    cd services/oauth-relay && npm ci --no-audit --no-fund && npm test

# Build the image the way the 1-click deploy does (linux/amd64).
image:
    docker build --platform linux/amd64 --build-arg ZOEN_REVISION="$(git rev-parse HEAD)" -t zoen:check .

# In-image checks against `just image` (no network, no credentials).
image-test:
    docker run --rm --user hermes --platform linux/amd64 --network none --read-only --tmpfs /tmp \
        -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python zoen:check -B /workspace/tests/integration_image.py
    docker run --rm --user hermes --platform linux/amd64 --network none \
        -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python zoen:check -B /workspace/tests/tasks_image.py
    docker run --rm --user hermes --platform linux/amd64 --network none \
        -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python zoen:check -B /workspace/tests/catalog_image.py
    docker run --rm --user hermes --platform linux/amd64 --network none \
        -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python zoen:check -B /workspace/tests/browser_image.py
    docker run --rm --platform linux/amd64 --network none --entrypoint sh zoen:check -c \
        'head -1 /opt/hermes/plow-seed/SOUL.md | grep -qx "# Zoen on Plow" && ! test -e /etc/sudoers.d/zoen && test -z "$HERMES_YOLO_MODE" && echo image-identity-ok'

# Everything that runs without Docker.
check: test relay-test
