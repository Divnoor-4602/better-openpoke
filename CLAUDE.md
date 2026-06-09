# OpenPoke

## Code style

- Self-explanatory code over comments. Default to writing no comments.
- When a comment is genuinely needed (a non-obvious WHY, a hidden constraint, a workaround), write one concise single-line comment. No multi-line blocks, no docstrings unless the language requires them for tooling.
- Don't restate what the code does. Don't reference tasks, PRs, callers, or removed code.

## AssemblyAI

This project uses AssemblyAI for realtime transcription and voice agent features. AssemblyAI's API surface changed recently — do not rely on memorized parameter names.

Before writing any AssemblyAI code, consult these sources in order:

1. **Project skill** — `.claude/skills/assemblyai/SKILL.md` (and `references/` for deep dives). Always loaded as a Skill.
2. **MCP server** — `assemblyai-docs` (configured in `.mcp.json`, transport: HTTP, URL: `https://mcp.assemblyai.com/docs`). Tools: `search_docs`, `get_pages`, `list_sections`, `get_api_reference`.
3. **Living docs** — `https://www.assemblyai.com/docs/agent-instructions.md` and `https://www.assemblyai.com/docs/llms.txt` for anything the skill or MCP doesn't cover.

API key lives in the Convex environment as `ASSEMBLYAI_API_KEY`. Never expose it to the browser — mint short-lived realtime tokens via a Convex action.

## MCP servers (project-scoped, see `.mcp.json`)

- `assemblyai-docs` — AssemblyAI documentation
- `convex` — Convex backend introspection
- `railway` — Railway infra
