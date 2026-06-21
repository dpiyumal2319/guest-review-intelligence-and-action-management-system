#!/usr/bin/env bash
# Render mermaid diagram sources to vector PDFs for inclusion in the report.
# Requires mermaid-cli (mmdc) and a Chrome/Chromium available to puppeteer.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p figures
PCFG="diagrams/puppeteer.json"
COMMON=(-p "$PCFG" -b white -t neutral)

render() {
  local name="$1"; local extra="${2:-}"
  echo ">> rendering $name"
  # shellcheck disable=SC2086
  mmdc -i "diagrams/${name}.mmd" -o "figures/${name}.pdf" "${COMMON[@]}" $extra
}

render db-schema "--pdfFit -c diagrams/mermaid-er.json"
render seq-detection "--pdfFit"
render seq-resolve "--pdfFit"
render timeline "--pdfFit"

echo "All diagrams rendered to figures/*.pdf"
