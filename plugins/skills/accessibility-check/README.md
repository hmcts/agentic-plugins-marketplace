# Accessibility Check Skill

A WCAG 2.1 AA compliance checklist covering both automated (axe-core) and manual checks. Catches the ~30% of issues axe can detect AND lists the manual checks a human must do for the rest.

## Usage

Triggered automatically by natural-language intent. Examples:

```
Run an accessibility review of this page.
Check if this component is WCAG 2.1 AA compliant.
Add axe-core tests to the login form.
What manual accessibility checks do I need to do here?
```

## What it provides

- **Automated checks** — axe-core snippets for Selenium (Java), Playwright (Node), and Playwright (Python).
- **Manual checks table** — keyboard nav, focus visibility, screen reader, colour contrast, error identification, timeout warnings.
- **Failure classification** — Critical / Serious block deployment; Moderate / Minor log as issues.
- **Evidence requirements** — what to attach to a PR so reviewers can verify.

## Prerequisites

The automated check examples each require a test dependency — install the one that matches your stack:

| Stack | Package |
|-------|---------|
| Java / Selenium | `com.deque.html.axe-core:selenium` (Maven/Gradle) |
| Node / Playwright | `npm install --save-dev axe-playwright` |
| Python / Playwright | `pip install axe-playwright-python` |

No prerequisites for the manual checks table.

## Installation

```
/plugin install accessibility-check@agentic-plugins-marketplace
```

## Extending for your organisation

The skill is intentionally framework-agnostic. If your organisation mandates a specific component library (e.g. GOV.UK Frontend, Material UI, Carbon Design System) or a specific issue-tracking workflow (e.g. Jira tickets for Moderate findings), layer those rules in a separate overlay skill in your own `.claude/skills/` directory.
