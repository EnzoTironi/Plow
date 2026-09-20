#!/bin/sh
# plow-init, then wipe leftover Zoen files on this line's volume.
set -eu
HOME_DIR="${HERMES_HOME:-/var/lib/hermes}"
/opt/hermes/.venv/bin/python /etc/s6-overlay/scripts/plow-init.py
/opt/hermes/.venv/bin/python /opt/hermes/enable-zoen-face.py \
  "$HOME_DIR/config.yaml"
