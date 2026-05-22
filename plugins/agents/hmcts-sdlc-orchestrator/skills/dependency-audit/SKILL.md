---
name: dependency-audit
description: Audit dependency versions across CP repositories. Use when checking for version mismatches, outdated libraries, or parent POM alignment across context services.
---

# Dependency Audit

Scans CP repositories for dependency version inconsistencies, outdated libraries, and parent POM alignment issues.

## When to Use

- User asks to "check dependency versions", "audit dependencies", "find version mismatches"
- User wants to verify a specific library version across all repos
- User wants to check parent POM chain alignment
- Before upgrading a shared library to find all consumers

## Process

### Step 1: Determine Scope

Ask the user what to audit:

- **All context services** — scan all `cpp-context-*` repos
- **Specific repos** — scan named repositories
- **Specific dependency** — find all usages of a named dependency
- **Parent POM chain** — verify super-pom → parent-pom → service alignment

### Step 2: Extract Version Information

#### For Maven repos (`cpp-context-*`, `cp-*`)

Read `pom.xml` from each repo root and extract:

1. **Parent POM** — `<parent>` groupId, artifactId, version
2. **Properties** — `<properties>` block for version properties
3. **Direct dependencies** — any `<dependency>` with explicit versions (not managed)
4. **Plugin versions** — any plugins with explicit versions

Key properties to check across the parent POM chain:

| Property | Defined in | Controls |
|----------|-----------|----------|
| `cpp.framework.version` | Service POM | cp-framework-libraries version |
| `cpp.microservice-framework.version` | Service POM | cp-microservice-framework version |
| `cpp.event-store.version` | Service POM | cp-event-store version |
| `cpp.file-service.version` | Service POM | cp-file-service version |
| `cpp.platform-libraries.version` | Service POM | cpp-platform-libraries version |

#### For Gradle repos (`cp-audit-*`, `cp-auth-*`, `cpp-mbd-*`)

Read `build.gradle` and extract:

1. **Plugin versions** — Spring Boot, dependency-management
2. **Dependencies** — implementation, testImplementation blocks
3. **Ext properties** — version variables

#### For Node repos (`cpp-ui-*`)

Read `package.json` and extract:

1. **Angular version** — `@angular/core`
2. **Key dependencies** — ngrx, govuk-frontend, ngx-bootstrap
3. **Node/npm versions** — engines field or .nvmrc

### Step 3: Compare and Report

Generate a report grouped by finding type:

```
## Dependency Audit Report

### Parent POM Versions
| Repo | Parent Artifact | Parent Version |
|------|----------------|----------------|
| cpp-context-hearing | cp-maven-parent-pom | 1.2.3 |
| cpp-context-resulting | cp-maven-parent-pom | 1.2.4 |
...

### Framework Library Versions
| Repo | framework | microservice-fw | event-store | platform-libs |
|------|-----------|-----------------|-------------|----------------|
...

### Version Mismatches (Action Required)
- **cp-framework-libraries**: 5 repos on 2.1.0, 3 repos on 2.0.8 (latest: 2.1.0)
- **Spring Boot**: gradle repos split between 3.4.1 and 3.4.2

### Outdated Dependencies
- **[repo]**: dependency X is N versions behind latest
```

### Step 4: Recommend Actions

For each mismatch, provide:
- Which repos need updating
- The target version
- Whether it's a breaking change (major version bump)
- Suggested update order (shared libraries first, then consumers)

## Tips

- The parent POM chain is: `cp-maven-super-pom` → `cp-maven-parent-pom` → `cp-maven-framework-parent-pom` → service POM
- `cp-maven-common-bom` manages transitive dependency versions — check it for the canonical version of third-party libs
- Renovate bot creates automated PRs for dependency updates — check for open Renovate PRs before manually updating
- Framework library version changes often require coordinated releases across multiple context services
