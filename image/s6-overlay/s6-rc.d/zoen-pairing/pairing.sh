#!/bin/sh
# The user already texted. Send the prewritten bubbles, then return so the
# gateway can start. s6 runs this file; it does not run the oneshot `up` file
# as a shell script.
set -eu
PATH=/command:/usr/local/bin:/opt/hermes/.venv/bin:/usr/bin:/bin
export PATH

until /opt/hermes/.venv/bin/python /opt/hermes/plugins/zoen-face/whatsapp.py; do
  echo "zoen-pairing: owner's text not answered yet, retrying" >&2
  /bin/sleep 0.2
done
