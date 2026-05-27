#!/bin/bash
# Pick the first free TCP port on 127.0.0.1 from a candidate list.
# Usage: PORT=$(pick_port.sh 5000)   or   PORT=$(pick_port.sh "${PORT:-5000}")

pick_listen_port() {
  # macOS AirPlay Receiver often binds *:5000 (returns 403, not hibs-bet).
  local preferred="${1:-5001}"
  local p tried=()
  for p in "$preferred" 5001 5002 5010 8080 5000; do
    case " ${tried[*]} " in
      *" $p "*) continue ;;
    esac
    tried+=("$p")
    if ! lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "$p"
      return 0
    fi
  done
  echo "$preferred"
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  pick_listen_port "${1:-5000}"
fi
