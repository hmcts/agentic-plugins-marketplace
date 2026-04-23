---
name: generate-bdd-specs
description: Use when the user wants to convert acceptance criteria into Cucumber/Gherkin feature files, write a .feature file, or produce BDD scenarios for a story.
---

# Generate BDD Specs (Gherkin)

## Purpose
Convert approved ACs into well-formed Cucumber/Gherkin feature files.

## Format rules
- One feature file per story (`<PROJ-NNN>.feature` or equivalent naming)
- `Feature:` block contains the user story statement
- `Background:` for context shared by all scenarios in the file
- `Scenario:` for individual ACs
- `Scenario Outline:` + `Examples:` for data-driven variations
- Tags on each scenario: `@smoke`, `@regression`, `@accessibility`, `@negative`

## Language rules
- Gherkin steps must be in business language — no technical implementation detail
- Given = state setup (not "I click the login button")
- When = single action (not "I fill in the form and submit it")
- Then = observable outcome from the actor's perspective
- Avoid UI selectors, SQL, HTTP verbs, class names in Gherkin

## Template

```gherkin
@regression
Feature: [Story title — PROJ-NNN]
  As a [actor]
  I want [goal]
  So that [benefit]

  Background:
    Given the system is in [base state]
    And [shared precondition]

  @smoke
  Scenario: [Happy path — AC-001]
    Given [specific context]
    When [actor performs action]
    Then [expected outcome]
      And [secondary outcome if needed]

  @negative
  Scenario: [Failure mode — AC-002]
    Given [context]
    When [action with invalid input]
    Then [error is surfaced appropriately]
      And [no state change occurred]

  @accessibility
  Scenario: [Accessibility — AC-00N]
    Given [page/component is rendered]
    When [axe-core scan is run]
    Then [zero violations are reported at WCAG 2.1 AA level]

  Scenario Outline: [Data-driven scenario]
    Given [context with <variable>]
    When [action with <input>]
    Then [outcome is <expected>]

    Examples:
      | variable | input | expected |
      | ...      | ...   | ...      |
```

## Tagging convention
| Tag             | Meaning                                              |
|-----------------|------------------------------------------------------|
| @smoke          | Run on every deploy — critical path only             |
| @regression     | Full regression suite                                |
| @negative       | Error handling, invalid inputs, boundary failures    |
| @accessibility  | axe-core or manual WCAG check required               |
| @contract       | Cross-service contract test                          |
| @wip            | In progress — excluded from CI until removed         |
