#!/usr/bin/env bash
set -eu
explorador_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$explorador_dir/iniciar_explorador.py" "$@"
