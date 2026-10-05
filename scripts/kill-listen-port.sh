#!/usr/bin/env bash
# Usage: kill_listen_port 3000
# Stops processes using the given TCP port (Lab dev helper).

_port_pids() {
  local port="${1:?port required}"
  local found=""

  if command -v lsof >/dev/null 2>&1; then
    found="$(lsof -ti ":${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -z "${found}" ]]; then
      found="$(lsof -ti ":${port}" 2>/dev/null || true)"
    fi
    if [[ -z "${found}" ]]; then
      found="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
    fi
  fi

  if [[ -z "${found}" ]] && command -v fuser >/dev/null 2>&1; then
    found="$(fuser "${port}/tcp" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true)"
  fi

  if [[ -z "${found}" ]] && command -v ss >/dev/null 2>&1; then
    found="$(
      ss -tlnp "sport = :${port}" 2>/dev/null \
        | grep -o 'pid=[0-9]*' \
        | cut -d= -f2 \
        | sort -u \
        | tr '\n' ' ' \
        | xargs echo -n 2>/dev/null || true
    )"
  fi

  echo "${found}" | xargs echo -n 2>/dev/null || true
}

_port_in_use() {
  local port="${1:?port required}"
  if command -v ss >/dev/null 2>&1; then
    ss -tln "sport = :${port}" 2>/dev/null | grep -q ":${port}"
    return $?
  fi
  [[ -n "$(_port_pids "${port}")" ]]
}

kill_listen_port() {
  local port="${1:?port required}"
  local attempt=0
  local pids=""

  if ! _port_in_use "${port}"; then
    return 0
  fi

  while _port_in_use "${port}" && [[ "${attempt}" -lt 5 ]]; do
    attempt=$((attempt + 1))
    pids="$(_port_pids "${port}")"

    if [[ -n "${pids}" ]]; then
      echo "Stopping process(es) on port ${port}: ${pids}"
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
      sleep 0.4
      pids="$(_port_pids "${port}")"
      if [[ -n "${pids}" ]]; then
        # shellcheck disable=SC2086
        kill -9 ${pids} 2>/dev/null || true
        sleep 0.3
      fi
    elif command -v fuser >/dev/null 2>&1; then
      echo "Stopping listeners on port ${port} (fuser)…"
      fuser -k "${port}/tcp" >/dev/null 2>&1 || true
      sleep 0.4
    else
      echo "Port ${port} is in use but could not find PID (install lsof, fuser, or ss)." >&2
      return 1
    fi
  done

  if _port_in_use "${port}"; then
    if command -v fuser >/dev/null 2>&1; then
      echo "Port ${port} still in use — trying fuser -k …"
      fuser -k "${port}/tcp" >/dev/null 2>&1 || true
      sleep 0.4
    fi
  fi

  if _port_in_use "${port}"; then
    echo "Port ${port} is still in use after kill attempts." >&2
    return 1
  fi
}
