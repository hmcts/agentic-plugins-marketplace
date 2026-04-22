# BDD Workflow Skill

Two skills that compose into a requirement-to-Gherkin pipeline:

1. **write-acceptance-criteria** — derive testable Given/When/Then acceptance criteria from a requirement or story.
2. **generate-bdd-specs** — convert those acceptance criteria into Cucumber/Gherkin `.feature` files with proper tagging.

Install the plugin once; get both skills.

## Usage

Triggered automatically by natural-language intent. Examples:

```
Write acceptance criteria for this story: "As a user I want to reset my password by email."
Turn these ACs into Given/When/Then.
Generate a .feature file from these acceptance criteria.
Produce BDD scenarios for the checkout flow.
```

## What it produces

### Acceptance criteria (write-acceptance-criteria)

Given/When/Then statements, one observable outcome per AC, covering happy path, failure modes, boundaries, and NFR thresholds. Concrete values ("status 200", "within 3 seconds") instead of vague language.

### Gherkin feature files (generate-bdd-specs)

`.feature` files using business language — no UI selectors, no HTTP verbs, no class names. Proper `Feature:`, `Background:`, `Scenario:`, `Scenario Outline:` structure. Tagged with `@smoke`, `@regression`, `@negative`, `@accessibility`, `@contract`, or `@wip`.

## Workflow

1. Invoke `write-acceptance-criteria` on a user story → get structured ACs.
2. Invoke `generate-bdd-specs` on those ACs → get a ready-to-run `.feature` file.
3. Hand the `.feature` file to Cucumber / Serenity / SpecFlow / behave for execution.

## Installation

```
/plugin install bdd-workflow@agentic-plugins-marketplace
```
