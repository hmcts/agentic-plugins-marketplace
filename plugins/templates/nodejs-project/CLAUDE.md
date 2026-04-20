# Project instructions for Claude

## Overview

<!-- Replace this section with a one-paragraph description of your project. -->

This is a Node.js project. Follow the conventions below when making changes.

## Tech stack

- **Runtime**: Node.js 22+ (LTS)
- **Language**: TypeScript 5+
- **Package manager**: npm (use `npm ci` in CI, `npm install` locally)
- **Testing**: Vitest
- **Linting / formatting**: ESLint + Prettier
- **Build**: tsc / tsup

## Project structure

```
src/
  index.ts          ← entry point
  ...
tests/
  unit/             ← fast, no I/O
  integration/      ← may hit real services; opt-in only
dist/               ← compiled output (gitignored)
package.json
tsconfig.json
```

## Development commands

```bash
npm install                  # install dependencies
npm run dev                  # start dev server / watch mode
npm test                     # run unit tests
npm run test:integration     # run integration tests
npm run lint                 # ESLint check
npm run format               # Prettier format
npm run build                # compile TypeScript
npm run typecheck            # tsc --noEmit
```

## Conventions

- Strict TypeScript — no `any`, no `@ts-ignore` without a comment explaining why.
- Use ES modules (`import`/`export`), not CommonJS `require`.
- All async functions must handle errors — no unhandled promise rejections.
- Prefer `const` over `let`; avoid `var`.
- Do not commit secrets. Use environment variables and `.env` files (gitignored).

## Testing guidelines

- Unit tests must be fast and have no external I/O; mock everything at the boundary.
- Integration tests must be tagged and not run by default.
- Name test files `*.test.ts`; describe blocks should match the module name.
- Each `it`/`test` block should test exactly one behaviour.

## What Claude should NOT do

- Do not run integration tests unless explicitly asked.
- Do not modify `package.json` dependencies without discussion.
- Do not introduce `require()` or CommonJS patterns.
- Do not commit directly to `main`; create a branch and open a PR.
