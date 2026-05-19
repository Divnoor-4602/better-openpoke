---
description: Full-stack deslop review (frontend `apps/web/` + backend `server/`) of uncommitted + recent commits using all installed skills
argument-hint: "[days=7] [base=main]"
---

You are running a **deslop review** of OpenPoke. The goal is to catch low-quality, sloppy, or anti-pattern code before it lands.

The review covers **two paths**, each with its own skill set:

- **Frontend** — `apps/web/`
- **Backend** — `server/`

Skip everything else (packages/sdk/, scripts/, etc.).

## Scope of review — per path

For BOTH `apps/web/` and `server/`, gather code from three sources in this order:

1. **Uncommitted changes** under the path (staged + unstaged + untracked):
   - `git status --short -- <path>/`
   - `git diff -- <path>/` (unstaged)
   - `git diff --cached -- <path>/` (staged)
   - For untracked files, read each one in full.

2. **Current branch commits** touching the path, ahead of `$2` (default `main`):
   - `git log --no-merges main..HEAD -- <path>/`
   - `git diff main...HEAD -- <path>/`

3. **Recent commits on this branch from the last $1 days** (default `7`):
   - `git log --since="$1 days ago" --no-merges -- <path>/`
   - For each commit, fetch `git show <sha> -- <path>/`.
   - If branch commits already cover the window, skip duplicates.

Parallelize: run all six git commands (3 per path) in a single message.

## How to use the skills

Apply EVERY relevant skill to the gathered diff/file set. For each finding, cite the skill name, the file:line, and the specific rule violated.

### Frontend skills (`apps/web/`)

- **web-design-guidelines** — a11y, perf, UX, semantic HTML, color/contrast, focus states.
- **vercel-react-best-practices** — React 19 patterns, `use`/Suspense, key usage, memo discipline, effects, the React Compiler implications (this project has `babel-plugin-react-compiler` enabled).
- **vercel-composition-patterns** — boolean prop proliferation, slot/children composition, headless patterns. Check `apps/web/src/components/ui/*` especially.
- **building-components** — accessible, composable, themeable component APIs. Cross-check shadcn primitives.
- **ai-sdk** — anything importing `ai`, `@ai-sdk/react`, streaming chat, tool calls. Project uses `ai@^6`.
- **streamdown** — markdown rendering safety / streaming patterns wherever `streamdown` is used.
- **no-use-effect** — flag direct `useEffect` outside reusable hooks.
- **props-object** — components with more than 6 props must accept one typed props object.

### Backend skills (`server/`)

- **fastapi-patterns** — `Annotated[X, Depends()]` deps (never `= Depends()`); `ERROR_RESPONSES: dict[int | str, dict[str, Any]]` typed at source; `JSONResponse.body` decoded via `bytes(...)`; `RequestResponseEndpoint` for `call_next`; Pydantic v2 `ClassVar[ConfigDict]` for `model_config`; `model_validate(dict)` instead of `Model(**dict)` for loose dicts; `_ =` discard for `app.middleware(...)`; required-before-defaulted parameter ordering when converting to Annotated.
- **basedpyright-strict** — `object` over `Any`; double-cast pattern `cast(T, cast(object, x))` for sqlite/json/external-library boundaries; `_ =` prefix for any ignored return (`reportUnusedCallResult`); annotated class attrs when class isn't `@final` (including `__slots__: tuple[str, ...]` and `model_config: ClassVar[ConfigDict]`); `@override` on unittest `TestCase` `setUp`/`tearDown`; lazy `__getattr__` returns `object`; Protocol pattern for untyped third-party libs and to break import cycles; boundary-only `# pyright: ignore[reportRule]` with specific rule names. Forbid: `cast(Any, x)`, blanket `# type: ignore`, relaxed severities.

If you see Python in `server/`, both backend skills MUST be applied. Do not silently skip basedpyright-strict because "the file already looks clean" — run `/Users/divnoor/anaconda3/envs/better-openpoke/bin/basedpyright server <changed-file>` for any non-trivial change and surface real diagnostics in the report.

## Stack constraints to remember

- React 19 + TanStack Start (NOT Next.js — do not suggest Next-only APIs like `next/image`, `app/` router, server actions).
- Vite + Tailwind v4 + shadcn.
- Import alias: `@/*` → `apps/web/src/*` (see `feedback_import_alias.md` in memory). Flag any `#/*` imports as violations even though `package.json` still declares `#/*` — the project standard is `@/*`.
- Package manager: **bun** (use `bun`/`bunx`, never `npm`/`pnpm`/`yarn` in suggestions).
- TypeScript strict.

## Output format

Produce a single markdown report with these sections:

1. **Scope summary** — count of files reviewed, commit SHAs touched, time window.
2. **Findings by severity** (`Critical` / `High` / `Medium` / `Low` / `Nit`). For each finding:
   - `file:line` — one-line description
   - **Skill:** which skill flagged it
   - **Rule:** the specific rule name/id
   - **Fix:** concrete code suggestion (diff-style if short)
3. **Patterns worth keeping** — non-obvious good calls in the changes (so the user knows what to repeat).
4. **Suggested next actions** — ordered checklist.

Be terse. No filler. If a section is empty, write "none" — don't pad.

## Execution rules

- Run the git commands yourself; do not ask the user to paste diffs.
- If a file is large, read the relevant ranges only.
- Do not run tests, builds, or write fixes unless explicitly asked — this is a review, not a patch.
- Parallelize all git reads in a single message.
