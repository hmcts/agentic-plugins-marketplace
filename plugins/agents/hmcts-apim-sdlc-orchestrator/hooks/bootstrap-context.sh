#!/usr/bin/env bash
# Auto-bootstraps .claude/CLAUDE.md for api-cp-* and service-cp-* repos on session start.
# Idempotent — skips if the file already references hmcts-apim-sdlc-orchestrator/context.
REPO_NAME=$(basename "$PWD")

if [[ "$REPO_NAME" == api-cp-* ]]; then
  CONTEXT_FILE="api-spec-shared.md"
elif [[ "$REPO_NAME" == service-cp-* ]]; then
  CONTEXT_FILE="service-shared.md"
else
  exit 0
fi

if [ -f ".claude/CLAUDE.md" ] && grep -q "hmcts-apim-sdlc-orchestrator/context" .claude/CLAUDE.md && grep -q "hmcts-standards.md" .claude/CLAUDE.md; then
  exit 0
fi

mkdir -p .claude
printf '%s\n%s\n%s\n%s\n' \
  "@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/shared-code-rules.md" \
  "@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/hmcts-standards.md" \
  "@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/${CONTEXT_FILE}" \
  "@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/claude-md-standards.md" \
  > .claude/CLAUDE.md

grep -q "\.claude/CLAUDE\.md" .gitignore 2>/dev/null || echo ".claude/CLAUDE.md" >> .gitignore

printf '{"systemMessage": "hmcts-apim-sdlc-orchestrator: context bootstrapped for %s"}\n' "$REPO_NAME"