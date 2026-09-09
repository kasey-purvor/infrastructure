#!/usr/bin/env bash
# bootstrap.sh — make every tool in this repo runnable on a fresh machine.
#
#   ./bootstrap.sh            # clone missing nested repos, build what isn't built
#   ./bootstrap.sh --force    # rebuild / reinstall everything
#
# Three manifests below are the ONLY things to edit when a tool is added:
#   NESTED_REPOS  dirs this repo's .gitignore excludes because they are their
#                 own git repos (see .gitignore) -> cloned if absent
#   NODE_BUILDS   dirs with a package.json build script -> npm ci && npm run build
#   PYTHON_TOOLS  dirs with a pyproject [project.scripts] -> uv tool install
#   BIN_LINKS     "<name> <path under tools/>" -> ~/.local/bin/<name> symlink (no build)
#
# Called by dev-environment/scripts/provision.sh (step 6) and runnable by
# hand. Idempotent; a failure in one tool warns and moves on (exit 1 at the
# end so the caller can tell). BOOTSTRAP_PYTHON pins uv's interpreter.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$HERE/tools"
FORCE="${1:-}"

NESTED_REPOS=(
  "ticket-panel          https://github.com/kasey-purvor/ticket-panel.git"
  "claude-hooks          https://github.com/kasey-purvor/claude-hooks.git"
  "mcp-d2-diagrams       https://github.com/kasey-purvor/mcp-d2-diagrams.git"
  "mcp-markdown-to-pdf   https://github.com/kasey-purvor/mcp-markdown-to-pdf.git"   # fork + MCP wrapper; upstream: simonhaenisch/md-to-pdf
  "mcp-trello            https://github.com/kocakli/Trello-Desktop-MCP.git"
  "mcp-google-workspace  https://github.com/taylorwilsdon/google_workspace_mcp.git"
)
NODE_BUILDS=(
  scrapfly-mcp          # workspaces: one build at the root covers packages/*
  mcp-d2-diagrams
  mcp-markdown-to-pdf
  mcp-trello
)
PYTHON_TOOLS=(
  ticket-panel
)
BIN_LINKS=(   # single-file tools exposed on PATH as ~/.local/bin/<name> -> tools/<path>
  "graph-mail            graph-mail/graph-mail.mjs"
)

log()  { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[bootstrap] WARN:\033[0m %s\n' "$*" >&2; FAILED=1; }
have() { command -v "$1" >/dev/null 2>&1; }
FAILED=0

# --- 1. nested repos ---------------------------------------------------------
# Auth: gh's credential helper if gh is present (private repos need it);
# public upstreams clone either way.
gitc() { if have gh; then git -c credential.helper='!gh auth git-credential' "$@"; else git "$@"; fi; }
for entry in "${NESTED_REPOS[@]}"; do
  read -r name url <<<"$entry"
  dst="$TOOLS/$name"
  if [ -d "$dst/.git" ]; then continue; fi
  if [ -e "$dst" ] && [ -n "$(ls -A "$dst" 2>/dev/null)" ]; then warn "$name: exists but is not a git checkout — leaving alone"; continue; fi
  log "cloning $name"
  gitc clone --quiet "$url" "$dst" || warn "$name: clone failed ($url)"
done

# --- 2. node builds ----------------------------------------------------------
if ! have node && [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
  # provision runs in a non-login shell; nvm is not sourced there
  . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"; nvm use default >/dev/null 2>&1 || true
fi
is_built() {  # build/ or dist/ at the dir, or packages/*/build for workspaces
  [ -d "$1/build" ] || [ -d "$1/dist" ] || ls -d "$1"/packages/*/build >/dev/null 2>&1
}
for name in "${NODE_BUILDS[@]}"; do
  dir="$TOOLS/$name"
  [ -f "$dir/package.json" ] || { warn "$name: no package.json (not cloned?)"; continue; }
  if [ "$FORCE" != "--force" ] && is_built "$dir"; then log "$name: built, skipping"; continue; fi
  have npm || { warn "$name: npm not on PATH — skipping node builds"; break; }
  log "building $name"
  ( cd "$dir" && npm ci --silent --no-audit --no-fund && npm run build --silent ) \
    || warn "$name: build failed"
done

# --- 3. python tools ---------------------------------------------------------
have uv || { warn "uv not on PATH — skipping python tools"; }
PY="${BOOTSTRAP_PYTHON:-$( [ -x "$HOME/miniconda3/bin/python3" ] && echo "$HOME/miniconda3/bin/python3" || command -v python3 || true)}"
for name in "${PYTHON_TOOLS[@]}"; do
  dir="$TOOLS/$name"
  have uv || break
  [ -f "$dir/pyproject.toml" ] || { warn "$name: no pyproject.toml (not cloned?)"; continue; }
  if [ "$FORCE" != "--force" ] && uv tool list 2>/dev/null | grep -q "^$name "; then log "$name: installed, skipping"; continue; fi
  log "installing $name (uv tool, python=${PY:-uv-managed})"
  if [ -n "$PY" ]; then
    UV_PYTHON_DOWNLOADS=never uv tool install --force --python "$PY" "$dir" >/dev/null || warn "$name: uv tool install failed"
  else
    uv tool install --force "$dir" >/dev/null || warn "$name: uv tool install failed"
  fi
done

# --- 4. bin links ------------------------------------------------------------
# Zero-build, single-file tools: just put them on PATH. Idempotent; a stale or
# foreign file at the link path is left alone and reported.
mkdir -p "$HOME/.local/bin"
for entry in "${BIN_LINKS[@]}"; do
  read -r name rel <<<"$entry"
  src="$TOOLS/$rel"; dst="$HOME/.local/bin/$name"
  [ -f "$src" ] || { warn "$name: $src missing (not cloned?)"; continue; }
  chmod +x "$src"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then continue; fi
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then warn "$name: $dst exists and is not a symlink — leaving alone"; continue; fi
  log "linking $dst -> $src"
  ln -sfn "$src" "$dst"
done

[ "$FAILED" = 0 ] && log "done" || { log "done with failures (see WARN lines)"; exit 1; }
