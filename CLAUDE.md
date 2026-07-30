# Infrastructure - Claude Context System

This repository contains self-hosted tools, services, and ideas for local infrastructure.

## How This System Works

Each project has its own `CLAUDE.md` with context. The folder structure serves as the source of truth:

```
infrastructure/
├── CLAUDE.md        # This file - root instructions
├── tools/           # Invoked on-demand (MCP servers, CLI tools, scripts)
│   ├── [name]/
│   │   ├── CLAUDE.md
│   │   └── sessions/    # Optional
│   └── archive/     # Deprecated tools, kept for reference
├── services/        # Always running (Docker containers, daemons, background processes)
│   ├── [name]/
│   │   ├── CLAUDE.md
│   │   └── sessions/    # Optional
│   └── archive/     # Deprecated services, kept for reference
└── jobs/            # Scheduled tasks (cron jobs, periodic automation)
    ├── [name]/
    │   ├── prompt.md    # Claude Code system prompt additions
    │   └── run.sh       # Entry point script (what cron calls)
    └── crontab          # Version-controlled cron schedule
```

**Tools vs Services vs Jobs:**
- **Tools**: Invoked when called, then stop. Examples: MCP servers, CLI utilities, build scripts
- **Services**: Run continuously in the background. Examples: Docker containers, databases, monitoring agents
- **Jobs**: Run on a schedule, do work, then exit. Examples: cron tasks, periodic Claude Code automation

**Archive folders** contain deprecated code that's no longer needed but worth keeping for reference. Ignore these unless explicitly told to look in them.

## Context Preservation Protocol

### Before Working on a Tool or Service
1. Read `tools/[name]/CLAUDE.md` or `services/[name]/CLAUDE.md` to understand current state
2. Note the **Current Status** and **Next Actions** sections
3. Check for any blockers or open questions

### During Work
- Note important decisions and why they were made
- Track discoveries, gotchas, and things that didn't work
- Keep Next Actions updated as you complete items

### Before Ending a Session
1. Update **Current Status** (state, last touched date, blockers)
2. Update **Next Actions** with what should happen next
3. Add any new **Decisions & Gotchas** discovered
4. Ask user if they want to log this session (for significant work)

### Session Logs (Optional)
Offer to create a session log when:
- Completing items from Next Actions
- Making architectural decisions
- Discovering gotchas worth documenting
- User explicitly requests it

Location: `[tools|services]/[name]/sessions/YYYY-MM-DD.md`
Contents: What was done, decisions made, discoveries, blockers encountered

## Starting a New Tool, Service, or Idea

1. Decide category: `tools/` (on-demand) or `services/` (always running)
2. Create folder: `tools/[name]/` or `services/[name]/`
3. Create `CLAUDE.md` using the template below
4. Set **State** to "Idea" or "Researching"
5. Add to the appropriate index below

Ideas get folders even before any code exists. The folder signals intent to explore.

## CLAUDE.md Template (Tools & Services)

```markdown
# [Tool Name]

## What & Why
> Brief description and the problem this solves

## Current Status
- **State**: [Idea | Researching/Planning | Cloned/Untested | Building | Working]
- **Last touched**: [date]
- **Blockers**: [none | list]

## Next Actions
- [ ] Immediate next step
- [ ] Following step
- [ ] Open questions to resolve

## Architecture
[Technical overview - how it works, key files, data flow]
[For ideas: skip or note "TBD"]

## Development
[Commands, ports, environment setup, how to run/test]
[For ideas: skip or note "TBD"]

## Decisions & Gotchas
[Why things are the way they are, things that bite]
[For ideas: note any constraints or requirements discovered]

## Ideas & Future
[Features considered, out of scope, maybe-later items]
```

## Tool Index

| Tool | State | Description |
|------|-------|-------------|
| firecrawl | Cloned/Untested | Web scraper API |
| llm-council | Cloned/Untested | Multi-LLM deliberation system |
| mcp-google-workspace | Cloned/Untested | Google Workspace MCP (Gmail, Drive, Calendar, Docs, etc.) |
| mcp-mermaid | Working | Mermaid diagram MCP server |
| mcp-markdown-to-pdf | Working | Markdown to PDF MCP server |
| mcp-c4-diagrams | Idea | C4 architecture diagrams — likely a skill layer on D2, not a separate server |
| mcp-d2-diagrams | Building | D2 diagram MCP server (modern Mermaid alternative). D2 binary installed, server not yet scaffolded |
| image-harvester | Building | Harvest all images from an Instagram profile via ScrapFly (enumerate via API, download binaries direct), saved to disk + manifest. Python CLI, not an MCP server. |

## Service Index

| Service | State | Description |
|---------|-------|-------------|
| *None yet* | | |

## Job Index

| Job | State | Description |
|-----|-------|-------------|
| *None yet* | | |

## Running Claude Code as a Scheduled Job

Jobs can launch Claude Code in headless mode (`-p`) with task-specific prompts and pre-approved tools.

**Basic pattern:**
```bash
claude -p \
  --append-system-prompt-file ./jobs/[name]/prompt.md \
  --allowedTools "Read,Bash(git status *)" \
  --max-turns 5 \
  --max-budget-usd 2.00 \
  --output-format json \
  "Task description here"
```

**Key flags:**
| Flag | Purpose |
|------|---------|
| `-p` | Headless/non-interactive mode (required for cron) |
| `--append-system-prompt-file` | Adds job-specific instructions to default prompt |
| `--allowedTools` | Pre-approves tools so no interactive prompts |
| `--max-turns` | Caps agentic iterations |
| `--max-budget-usd` | Cost ceiling per run |
| `--output-format json` | Machine-parseable output |
| `--model` | Override model (e.g. `claude-sonnet-4-6` for cheaper jobs) |

## State Definitions

- **Idea**: Initial concept, no code yet
- **Researching/Planning**: Exploring feasibility, gathering requirements, designing approach
- **Cloned/Untested**: Repository pulled but not yet configured or tested for local setup
- **Building**: Active development
- **Working**: Functional, in use

## MCP Server Naming Convention

All MCP (Model Context Protocol) servers should follow these naming standards for consistency.

### Folder Names
**Pattern**: `mcp-{descriptive-slug}`
- Always prefix with `mcp-` to identify as an MCP server
- Use full words, not abbreviations (e.g., `markdown` not `md`)
- Use kebab-case for multi-word names

Examples:
- ✓ `mcp-mermaid`
- ✓ `mcp-markdown-to-pdf`
- ✓ `mcp-c4-diagrams`
- ✗ `md-to-pdf-mcp` (wrong position, abbreviation)
- ✗ `c4-diagrams-mcp` (suffix instead of prefix)

### MCP Server Names (in code)
**Pattern**: Match the folder name exactly

```typescript
const server = new Server({
  name: 'mcp-markdown-to-pdf',  // Matches folder name
  version: '1.0.0',
});
```

### Tool Names (what LLMs see and call)
**Pattern**: `{verb}_{object}` - action-first, snake_case

The tool name is what AI agents see when querying available tools and use to invoke them. Make it descriptive and action-oriented.

Examples:
- ✓ `generate_mermaid_diagram`
- ✓ `convert_markdown_to_pdf`
- ✓ `create_c4_diagram`
- ✗ `markdown_to_pdf` (missing verb)
- ✗ `mcp_generate_diagram` (don't prefix with mcp)

### Tool Descriptions (guiding AI behavior)
Tool descriptions should include instructions for AI agents about required information. Use phrases like:
- "IMPORTANT: Before calling this tool, confirm with the user..."
- "Ask the user for X if not specified"
- "This parameter is required - if not provided, ask the user"

This guides LLMs to gather necessary information before invoking tools.

### Internal Code (functions, classes, variables)
- Follow language conventions (camelCase for JS/TS)
- No `mcp` prefix needed - these are internal implementation details
- Keep descriptive: `renderMermaid()`, `convertMarkdownToPdf()`

### Summary Table

| Item | Pattern | Example |
|------|---------|---------|
| Folder | `mcp-{slug}` | `mcp-markdown-to-pdf` |
| Server name | Match folder | `mcp-markdown-to-pdf` |
| Tool name | `{verb}_{object}` | `convert_markdown_to_pdf` |
| Functions | camelCase | `convertMarkdownToPdf()` |

