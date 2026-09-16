# Zoen: Hermes software factory on the official Plow Hermes base.
#
# Pin by immutable tag + digest. A moving tag would substitute code under an
# agent that holds a live Plow credential.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-80ef5024eb4b770e727a618a9b55421c73da6228@sha256:864771e8165db16c11a55635df85696f39d91020f258576dd62b7cab0515514f

# --yolo: frozen into tools.approval at gateway import. Tirith /approve
# otherwise parks the turn on iMessage while the owner only sees typing.
ENV HERMES_YOLO_MODE=1

# plow-init composes SOUL.md on every boot as the base persona plus this file.
# Do not COPY to /var/lib/hermes/SOUL.md. It is overwritten at boot.
COPY runtime/persona.md /opt/hermes/plow-seed/persona.md
COPY runtime/bootstrap.md /opt/hermes/plow-seed/bootstrap.md
COPY LICENSE NOTICE docs/zoen-card.jpg /usr/share/doc/zoen/
RUN chmod 0644 /opt/hermes/plow-seed/persona.md /opt/hermes/plow-seed/bootstrap.md

# Scanner + canvas CLIs (deterministic). Node 22 if the base is older.
# gh is GitHub (PRs, comments, merge). Prove-as-user is skill prove.
# Skills COPY after this so a playbook edit does not reinstall scanners.
ARG NODE_VERSION=22.19.0
ARG GH_VERSION=2.101.0
RUN set -eu; \
    if command -v node >/dev/null 2>&1 \
       && node -e 'process.exit(Number(process.versions.node.split(".")[0] < 22))'; then \
      echo "node $(node -v)"; \
    else \
      arch=$(uname -m); \
      case "$arch" in \
        x86_64) na=x64 ;; \
        aarch64) na=arm64 ;; \
        *) echo "unsupported arch $arch" >&2; exit 1 ;; \
      esac; \
      curl -fsS --max-time 120 \
        "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${na}.tar.xz" \
        | tar -xJ -C /usr/local --strip-components=1; \
    fi; \
    npm install -g @alibaba-group/open-code-review@^1 deepsec@^2 @coldtea/pr-lens-cli; \
    command -v ocr >/dev/null; \
    command -v deepsec >/dev/null; \
    command -v pr-lens >/dev/null; \
    if command -v gh >/dev/null 2>&1; then \
      echo "gh $(gh --version | head -n 1)"; \
    else \
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
    command -v gh >/dev/null

# Usage reporter: fetch the commit vendor/client.pin names, refuse any other hash.
COPY vendor/client.pin /opt/plow/agent-index-client.pin
RUN set -eu; \
    sha="$(sed -n 's/^sha=//p' /opt/plow/agent-index-client.pin)"; \
    want="$(sed -n 's/^sha256=//p' /opt/plow/agent-index-client.pin)"; \
    path="$(sed -n 's/^path=//p' /opt/plow/agent-index-client.pin)"; \
    curl -fsS --max-time 60 -o /opt/plow/agent-index-client.py \
      "https://raw.githubusercontent.com/plow-pbc/agent-index-client/${sha}/${path}"; \
    got="$(sha256sum /opt/plow/agent-index-client.py | cut -d' ' -f1)"; \
    [ "$got" = "$want" ] || { echo "agent-index client is $got, pin says $want" >&2; exit 1; }

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
 && find /opt/plow -type f -exec chmod 0644 {} +

COPY image/plugins/zoen-face/ /opt/hermes/plugins/zoen-face/
COPY image/enable-zoen-face.py /opt/hermes/enable-zoen-face.py
COPY image/plow-init-then-face.sh /opt/hermes/plow-init-then-face.sh
COPY image/s6-overlay/ /etc/s6-overlay/
RUN chmod 0644 /opt/hermes/plugins/zoen-face/plugin.yaml /opt/hermes/plugins/zoen-face/__init__.py /opt/hermes/plugins/zoen-face/quiet.py /opt/hermes/enable-zoen-face.py \
 && chmod 0755 /opt/hermes/plow-init-then-face.sh \
 && chmod 0755 /etc/s6-overlay/s6-rc.d/agent-index/run \
 && chmod 0755 /etc/s6-overlay/s6-rc.d/zoen-floor-cron/run \
 && /opt/hermes/.venv/bin/python /opt/hermes/enable-zoen-face.py
