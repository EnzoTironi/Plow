#!/bin/sh
# plow-init, then drop obsolete Zoen config. The home volume stays.
set -eu
HOME_DIR="${HERMES_HOME:-/var/lib/hermes}"
/opt/hermes/.venv/bin/python /etc/s6-overlay/scripts/plow-init.py
/opt/hermes/.venv/bin/python /opt/hermes/enable-zoen-face.py \
  "$HOME_DIR/config.yaml"
# A previous image wrote Zoen secrets as root. The gateway runs as hermes.
if [ "$(id -u)" = 0 ] && id hermes >/dev/null 2>&1; then
  mkdir -p "$HOME_DIR/zoen"
  chown -R hermes:hermes "$HOME_DIR/zoen"
  chmod 700 "$HOME_DIR/zoen"
  find "$HOME_DIR/zoen" -type f -exec chmod 600 {} +
fi
