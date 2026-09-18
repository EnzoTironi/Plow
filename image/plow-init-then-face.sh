#!/bin/sh
# Runs after plow-init so live config.yaml keeps zoen-face and the model map.
set -eu
/opt/hermes/.venv/bin/python /etc/s6-overlay/scripts/plow-init.py
/opt/hermes/.venv/bin/python /opt/hermes/enable-zoen-face.py \
  "${HERMES_HOME:-/var/lib/hermes}/config.yaml"
