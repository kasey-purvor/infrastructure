# mcp-c4-diagrams

## What & Why
> An MCP server for generating C4 architecture diagrams. C4 provides a hierarchical approach to visualizing software architecture at different levels of abstraction (Context, Container, Component, Code).

## Current Status
- **State**: Idea (research done, no implementation)
- **Last touched**: 2026-02-27
- **Blockers**: Depends on mcp-d2-diagrams being built first (D2 is the likely rendering backend)

## Next Actions
- [ ] Decide whether this needs its own MCP server or can be a skill/prompt layer on top of mcp-d2-diagrams
- [ ] If separate server: decide rendering backend (D2 preferred, PlantUML alternative)
- [ ] If skill-only: create a C4-specific skill that generates D2 code following C4 conventions

## Key Research Finding (2026-02-27)
**C4 is a methodology/notation, NOT a tool or renderer.** There is no "C4 binary" to install. C4 defines:
- 4 hierarchical zoom levels (Context, Container, Component, Code)
- Standard box types (Person, System, Container, Component) with required metadata
- Conventions for what each diagram level should show

Various tools *implement* C4 rendering:
- **Structurizr** — Simon Brown's (C4 creator) own tool. Java-based, model-first DSL. Best for persistent architecture models maintained over time.
- **C4-PlantUML** — PlantUML macros for C4 shapes. Popular in enterprise.
- **Mermaid** — Built-in C4 diagram types (C4Context, C4Container, etc.). Basic but functional.
- **D2** — No native C4 support, but can render C4-style diagrams by convention (styling boxes appropriately).

### Practical Conclusion
For the "generate me a C4 diagram on demand" use case, the pragmatic approach is:
1. Build mcp-d2-diagrams first (general-purpose diagramming)
2. Create a skill that instructs the LLM to generate D2 code following C4 conventions
3. Only build a dedicated C4 MCP server if the skill approach proves insufficient

A dedicated MCP server (Structurizr-based) only makes sense if maintaining a persistent architecture model across multiple diagrams — that's a documentation workflow tool, not an on-demand diagram generator.

## Architecture
TBD — likely a skill layer on top of D2 rather than a separate MCP server

## Development
TBD

## Decisions & Gotchas
- C4 is a methodology, not software. Don't confuse it with its rendering tools.
- Structurizr is the "official" C4 tool but is Java-based and overkill for on-demand generation.
- D2 can render C4-style diagrams without any C4-specific tooling — just needs the right conventions in the D2 syntax.

## Ideas & Future
- Support all 4 C4 levels (Context, Container, Component, Code)
- C4 colour conventions (blue for internal systems, grey for external, etc.)
- Integration with mcp-d2-diagrams for rendering
- Possible Structurizr integration if persistent model management is needed later
