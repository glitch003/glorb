#!/bin/sh
# Launch the glorb LED server: web UI + E1.31 output to the Angios.
# Binds 0.0.0.0 so you can open the UI from a phone on the glorb network.
cd "$(dirname "$0")"
exec python3 -m glorbleds serve --host 0.0.0.0 "$@"
