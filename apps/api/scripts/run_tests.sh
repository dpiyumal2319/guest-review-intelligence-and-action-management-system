#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ] || ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  rm -rf .venv
  if python3 -m venv .venv >/dev/null 2>&1; then
    :
  else
    rm -rf .venv
    python3 -m venv --without-pip .venv
  fi
fi

if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  get_pip="$(mktemp)"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$get_pip"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$get_pip" https://bootstrap.pypa.io/get-pip.py
  else
    echo "pip is missing and neither curl nor wget is available to bootstrap it." >&2
    exit 1
  fi
  .venv/bin/python "$get_pip"
  rm -f "$get_pip"
fi

if ! .venv/bin/python -m pytest --version >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi

.venv/bin/python -m pytest -s tests
