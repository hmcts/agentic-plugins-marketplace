---
name: accessibility-check
description: Use when the user wants to check accessibility, run an a11y review, verify WCAG 2.1 AA compliance, or add axe-core tests to a UI component or page.
---

# Accessibility Check

## Purpose
Ensure any user-facing output meets **WCAG 2.1 AA**. Combines automated checks (axe-core)
with the manual checks that cannot be fully automated.

## When to apply
- Any story that produces HTML output (pages, components, error messages, forms)
- Any story modifying navigation, focus management, or dynamic content

## Automated checks (axe-core)
Add the following assertion to the integration test for every new page or component.

```java
// Java / Selenium example
AxeBuilder axeBuilder = new AxeBuilder();
Results results = axeBuilder.analyze(driver);
assertThat(results.getViolations()).isEmpty();
```

```javascript
// Node / Playwright example
const { checkA11y } = require('axe-playwright');
await checkA11y(page, null, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } });
```

```python
# Python / Playwright example
from axe_playwright_python.sync_playwright import Axe
results = Axe().run(page)
assert results.violations_count == 0
```

## Manual checks (required for these scenarios)
Automation catches ~30% of issues. The rest need a human:

| Check                            | Guidance                                                  |
|----------------------------------|-----------------------------------------------------------|
| Keyboard navigation              | Tab through all interactive elements — logical order?     |
| Focus visible                    | Is the focus ring visible on all interactive elements?    |
| Screen reader (VoiceOver/NVDA)   | Are form labels, error messages, and headings announced?  |
| Colour contrast                  | 4.5:1 for normal text, 3:1 for large text                 |
| Error identification              | Errors linked to fields via `aria-describedby`            |
| Timeout warnings                 | User warned before session timeout with option to extend  |

## Failure classification
| Severity | Action                                                  |
|----------|---------------------------------------------------------|
| Critical | Block deployment — must fix before merge                |
| Serious  | Block deployment — must fix before merge                |
| Moderate | Log as an issue — fix within the current sprint         |
| Minor    | Log as an issue — fix in the next sprint                |

## Evidence to record
For the PR / deployment artefact:
- axe-core report (JSON or HTML export)
- Manual check results (simple pass/fail against the table above)
- Any waived items with justification linked to the story
