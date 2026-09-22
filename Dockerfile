# Zoen: personal agent on the official Plow Hermes base.
#
# Pin by immutable tag + digest. A moving tag would substitute code under an
# agent that holds a live Plow credential.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-ef0019372ff8bca593611b31ebd2e08f9f1458ff@sha256:a8a2f97ad78b8192d80a984dce81d3bf5a9a883d18cb7b677704913a09b56aee

# --yolo: frozen into tools.approval at gateway import. Tirith /approve
# otherwise parks the turn on iMessage while the owner only sees typing.
ENV HERMES_YOLO_MODE=1
ENV AGENT_ID=zoen
ENV AGENT_NAME=Zoen
ENV ZOEN_OAUTH_RELAY_URL=https://zoen-oauth-relay.agenttironi.workers.dev
ENV ZOEN_GOOGLE_RELAY_URL=https://zoen-oauth-relay.agenttironi.workers.dev

# gh is GitHub. espeak-ng is outbound voice. ffmpeg is already on the base.
# Language and review are the model's. A public page installs its tunnel on that turn.
ARG GH_VERSION=2.101.0
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl espeak-ng; \
    rm -rf /var/lib/apt/lists/*; \
    if ! command -v gh >/dev/null 2>&1; then \
      arch=$(uname -m); \
      case "$arch" in \
        x86_64) ga=amd64 ;; \
        aarch64) ga=arm64 ;; \
        *) echo "unsupported arch $arch" >&2; exit 1 ;; \
      esac; \
      curl -fsS --max-time 120 -L \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ga}.tar.gz" \
        | tar -xz -C /tmp; \
      install -m 0755 "/tmp/gh_${GH_VERSION}_linux_${ga}/bin/gh" /usr/local/bin/gh; \
      rm -rf "/tmp/gh_${GH_VERSION}_linux_${ga}"; \
    fi; \
    command -v gh >/dev/null; \
    command -v espeak-ng >/dev/null

# plow-init writes $HOME/SOUL.md from this file plus persona.md on every boot.
# Hermes injects that one file and truncates it past 20k characters.
# Zoen voice lives in persona.md. SOUL.md keeps the operating rules.
COPY runtime/SOUL.md /opt/hermes/plow-seed/SOUL.md
COPY runtime/persona.md /opt/hermes/plow-seed/persona.md
COPY runtime/bootstrap.md /opt/hermes/plow-seed/bootstrap.md
COPY LICENSE NOTICE docs/zoen-card.jpg /usr/share/doc/zoen/
RUN chmod 0644 /opt/hermes/plow-seed/SOUL.md /opt/hermes/plow-seed/persona.md /opt/hermes/plow-seed/bootstrap.md

# Bundled skills. The gateway reconciles this tree into $HERMES_HOME/skills
# on boot: new/untouched copies update, owner edits stay.
COPY skills/ /opt/hermes/skills/
RUN find /opt/hermes/skills -mindepth 1 -type d -exec chmod 0755 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f ! -perm -u+x -exec chmod 0644 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f -perm -u+x -exec chmod 0755 {} +

# Root-owned copies the supervisor and the agent both run.
# bundle / issues / watch / lens / react / register_cron / net.
COPY skills/zoen/scripts/ /opt/plow/zoen/
RUN chown -R root:root /opt/plow \
 && find /opt/plow -type d -exec chmod 0755 {} + \
 && find /opt/plow -type f -exec chmod 0644 {} + \
 && python3 /opt/plow/zoen/face.py bake --dest /usr/share/doc/zoen \
 && chmod 0644 /usr/share/doc/zoen/Zoen.vcf /usr/share/doc/zoen/Enzo.vcf

COPY image/plugins/zoen-face/ /opt/hermes/plugins/zoen-face/
COPY image/optional-mcps/ /opt/hermes/optional-mcps/
COPY image/enable-zoen-face.py /opt/hermes/enable-zoen-face.py
COPY image/plow-init-then-face.sh /opt/hermes/plow-init-then-face.sh
COPY image/s6-overlay/ /etc/s6-overlay/
RUN chmod 0644 /opt/hermes/plugins/zoen-face/plugin.yaml /opt/hermes/plugins/zoen-face/__init__.py /opt/hermes/plugins/zoen-face/quiet.py /opt/hermes/enable-zoen-face.py \
 && chmod 0755 /opt/hermes/plow-init-then-face.sh \
 && chmod 0755 /etc/s6-overlay/s6-rc.d/zoen-floor-cron/run \
 && chmod 0755 /etc/s6-overlay/s6-rc.d/zoen-pairing/run \
 && /opt/hermes/.venv/bin/python /opt/hermes/enable-zoen-face.py

# Public page copy does not invalidate the tool-install layers.
ENV AGENT_BLURB="life happens. text zoen. plan your week. find a great place. compare before you buy. walk into the meeting ready. find your next customer. turn an idea into something real. your apps and thousands of tools, in one conversation. big dreams. everyday problems. one little monster."

ARG ZOEN_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/EnzoTironi/plow" \
      org.opencontainers.image.revision=$ZOEN_REVISION \
      org.opencontainers.image.title="Zoen"
# The line volume keeps this stamp. A different image clears the "already sent" mark once.
RUN ZOEN_REVISION="$ZOEN_REVISION" python3 - <<'PY'
import hashlib, os, pathlib
digest = hashlib.sha256()
digest.update(os.environ.get("ZOEN_REVISION", "unknown").encode())
roots = [pathlib.Path("/opt/hermes/plugins/zoen-face"), pathlib.Path("/opt/plow/zoen/face.py")]
files = []
for root in roots:
    files.extend([root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file()))
for path in files:
    digest.update(path.as_posix().encode())
    digest.update(path.read_bytes())
pathlib.Path("/etc/zoen-image-id").write_text(digest.hexdigest() + "\n")
PY
