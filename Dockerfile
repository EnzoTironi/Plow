# Zoen: personal agent on the official Plow Hermes base.
#
# Pin by immutable tag + multi-arch index digest. A moving tag would substitute
# code under an agent that holds a live Plow credential. To bump, follow
# README "Bump the Plow base": the base SOUL.md fixture and its sha move with it.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-c692e807386993b677de13500ce3a1a323d52b48@sha256:e04a373ed7b8a1f6440e4813eb282c2b6087d31e77c6e5e386ae40a307163d32

# No HERMES_YOLO_MODE. It also waves through the plow_chat plugin's approval
# for email sent from the owner's Gmail. Commands Zoen runs in its own VM skip
# the prompt through `approvals.mode: off` (image/enable-zoen-face.py), and the
# gateway's approval ask now reaches the chat (zoen-face quiet.py).
ENV AGENT_ID=zoen
ENV AGENT_NAME=Zoen
ENV ZOEN_OAUTH_RELAY_URL=https://zoen-oauth-relay.agenttironi.workers.dev
ENV ZOEN_GOOGLE_RELAY_URL=https://zoen-oauth-relay.agenttironi.workers.dev

# gh is GitHub. espeak-ng is outbound voice. ffmpeg is already on the base.
# Language and review are the model's. A public page installs its tunnel on that turn,
# under $HOME (playbooks/show.md). No sudo: the agent runs as `hermes`, and a root
# grant would let any turn rewrite the root-owned SOUL.md, plugins and approval gates.
# gh is pinned by version and by the sha256 GitHub publishes in gh_<v>_checksums.txt.
ARG GH_VERSION=2.101.0
ARG GH_SHA256_AMD64=9bca2d1c16825f109907a23307628a2f0698fbf99662b73a5cf0b020293072b8
ARG GH_SHA256_ARM64=b57e8063f18862647c9d22727c32e9da1b963f8bf9db648fe123a6975695640f
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl espeak-ng; \
    rm -rf /var/lib/apt/lists/*; \
    if ! command -v gh >/dev/null 2>&1; then \
      arch=$(uname -m); \
      case "$arch" in \
        x86_64) ga=amd64; sum="$GH_SHA256_AMD64" ;; \
        aarch64) ga=arm64; sum="$GH_SHA256_ARM64" ;; \
        *) echo "unsupported arch $arch" >&2; exit 1 ;; \
      esac; \
      tarball="/tmp/gh_${GH_VERSION}_linux_${ga}.tar.gz"; \
      curl -fsS --max-time 120 -L -o "$tarball" \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ga}.tar.gz"; \
      echo "$sum  $tarball" | sha256sum -c -; \
      tar -xzf "$tarball" -C /tmp; \
      install -m 0755 "/tmp/gh_${GH_VERSION}_linux_${ga}/bin/gh" /usr/local/bin/gh; \
      rm -rf "$tarball" "/tmp/gh_${GH_VERSION}_linux_${ga}"; \
    fi; \
    command -v gh >/dev/null; \
    command -v espeak-ng >/dev/null

# Identity. plow-init writes $HOME/SOUL.md on every boot as the base SOUL.md
# followed by persona.md; Hermes truncates it past 20k characters.
# Zoen keeps the base file and adapts two passages with image/zoen-soul.py (the
# build fails if the base reworded them), so base rules reach Zoen on every bump.
# Zoen's own voice and operating rules live in persona.md (tests/test_persona.py
# keeps the composed file under 16k). bootstrap.md is the first-run ritual that
# context.py packs; plow-init does not read it.
COPY image/zoen-soul.py /opt/hermes/zoen-soul.py
COPY runtime/persona.md /opt/hermes/plow-seed/persona.md
COPY runtime/bootstrap.md /opt/hermes/plow-seed/bootstrap.md
COPY LICENSE NOTICE docs/zoen-card.jpg /usr/share/doc/zoen/
RUN python3 /opt/hermes/zoen-soul.py /opt/hermes/plow-seed/SOUL.md \
 && chmod 0644 /opt/hermes/plow-seed/SOUL.md /opt/hermes/plow-seed/persona.md /opt/hermes/plow-seed/bootstrap.md

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
 && chmod 0755 /etc/s6-overlay/s6-rc.d/zoen-pairing/up /etc/s6-overlay/s6-rc.d/zoen-pairing/pairing.sh \
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
