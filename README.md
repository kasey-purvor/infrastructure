# infrastructure

Self-authored tools, services, and jobs that live at `~/dev_wsl/infrastructure`.
This repo is the backup-of-record for everything here that exists nowhere else:
the Claude plugin (`tools/claude-plugins/my-design`), `claude-sessions`, `temps`,
`image-harvester`, the self-built MCP servers (`mcp-c4-diagrams`, `mcp-mermaid`,
`scrapfly-mcp`), and the top-level Claude context files.

## Separately-versioned tools (NOT tracked here — clone them in)

These directories are their own git repos with their own remotes; this repo
gitignores them so each has exactly one source of truth. On a fresh machine,
clone them back into place:

| Path | Remote |
|------|--------|
| `tools/ticket-panel` | `https://github.com/kasey-purvor/ticket-panel.git` |
| `tools/claude-hooks` | `https://github.com/kasey-purvor/claude-hooks.git` (private) |
| `tools/mcp-d2-diagrams` | `https://github.com/kasey-purvor/mcp-d2-diagrams.git` |
| `tools/mcp-markdown-to-pdf` | `https://github.com/simonhaenisch/md-to-pdf.git` (upstream) |
| `tools/mcp-trello` | `https://github.com/kocakli/Trello-Desktop-MCP.git` (upstream) |
| `tools/mcp-google-workspace` | `https://github.com/taylorwilsdon/google_workspace_mcp.git` (upstream) |

`tools/_archive/` (firecrawl, llm-council — abandoned upstream clones) is also
ignored; recover from upstream if ever needed.

## Consumers

Things that depend on this directory existing at `~/dev_wsl/infrastructure`:

- **dev-environment** (`kasey-purvor/dev-environment`): bind-mounts this dir
  into the container; `provision.sh` installs `ticket-panel` from it and
  registers the `my-design` plugin marketplace from
  `tools/claude-plugins/my-design`.
- **`~/.claude/hooks/`**: `orient-gate.sh`, `worktree-guard.sh`,
  `write-guard.sh` are symlinks into `tools/claude-hooks/`.
- **`~/.local/bin/claude-sessions`**: symlink to
  `tools/claude-sessions/claude_sessions.py`.
- **`.zshrc` `temps` alias**: runs `tools/temps/temps.py` via `uv run`.

## Secrets

Never commit secret values. `.gitignore` blocks `*.env`, bare `env`, `token`,
keys, and credentials; templates/examples (`*.env.template`, `*.env.example`)
are allowed. Runtime secrets live outside git and are re-created per machine.
