## What API Spec Repos Are

`api-cp-*` repos are **OpenAPI-first JAR libraries**. They produce no runnable application by default — their output is a published JAR containing generated Spring `@RequestMapping` interfaces and Lombok DTOs. Downstream `service-cp-*` repos declare them as dependencies and implement the generated interfaces.

Exception: a repo may be **hybrid** (spec + implementation) if it contains controller and service classes alongside the generated code. The repo-specific section below states which pattern applies.

## Commands

```bash
# Build
./gradlew build -DAPI_SPEC_VERSION=<version>   # full build with tests; version required in CI
./gradlew build                                 # local only — defaults to 0.0.999
./gradlew build -x test                         # skip tests

# Test
./gradlew test                                                        # all tests
./gradlew test --tests 'uk.gov.hmcts.cp.config.OpenApiObjectsTest'   # single class
./gradlew test --tests 'uk.gov.hmcts.cp.config.OpenApiObjectsTest.myMethod'  # single method
./gradlew check                                                       # tests + JaCoCo coverage

# Code generation
./gradlew openApiGenerate                       # regenerate from OpenAPI spec (runs automatically before compileJava)

# Code quality
./gradlew pmdMain                               # PMD static analysis
./gradlew spotlessCheck                         # formatting check
./gradlew spotlessApply                         # auto-fix formatting
./gradlew jacocoTestReport                      # coverage report → build/reports/jacoco/

# Publish
./gradlew publishToMavenLocal                   # local Maven cache — required before dependent service builds against local changes

# Lint OpenAPI spec
spectral lint "src/main/resources/openapi/*.{yml,yaml}"
```

`API_SPEC_VERSION` is generated from git history in CI via `hmcts/artefact-version-action@v1`. Locally any string works (`-DAPI_SPEC_VERSION=local`).

## Architecture: Code Generation Pipeline

**Source of truth**: `src/main/resources/openapi/openapi-spec.yml`

**JSON Schemas**: `src/main/resources/openapi/schema/*.schema.json`
- Each schema has a paired `*.example.json` validated by AJV in CI (`lint-openapi.yml`)
- The OpenAPI spec references these schemas via `$ref`

**Generated output** (`build/generated/src/main/java/uk/gov/hmcts/cp/openapi/`):
- `api/` — Spring `@RequestMapping` interfaces, one per OpenAPI tag
- `model/` — Lombok DTOs: `@Builder`, `@AllArgsConstructor`, `@NoArgsConstructor`, `@JsonInclude(NON_NULL)`

**Never edit files under `build/generated/` directly.** All model and interface changes go through the OpenAPI spec, then `./gradlew openApiGenerate`.

**Generator standard settings** (defined in `gradle/openapi.gradle`):
- Generator: `spring`, `interfaceOnly: true`
- `useTags: true`, `useSpringBoot3: true`
- `openApiNullable: false` — avoids `JsonNullable` wrapper types
- `generatedConstructorWithRequiredArgs: false` — prevents conflict with Lombok `@AllArgsConstructor`
- Type mapping: `OffsetDateTime` → `java.time.Instant`
- Model annotation: `@com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)` must be in `additionalModelTypeAnnotations`
- Input spec: use modern `inputSpec.set(layout.projectDirectory.file(...))` syntax — not the deprecated `inputSpec =` assignment

## Gradle Configuration Modules

| File | Purpose |
|---|---|
| `java.gradle` | Java 25 Temurin toolchain; `-Xlint:unchecked -Werror`; adds `build/generated/src/main/java` to main source set |
| `openapi.gradle` | OpenAPI Generator config; wires `openApiGenerate` before `compileJava` |
| `test.gradle` | JUnit Platform; JaCoCo XML+HTML; `failFast=true`; CI-friendly XML reports |
| `pmd.gradle` | PMD via `.github/pmd-ruleset.xml`; excludes generated code; not run during standard build |
| `repositories.gradle` | Maven Central + Azure Artifacts resolution; GitHub Packages + Azure Artifacts publishing |
| `dependency.gradle` | `dependencyUpdates` task rejects non-stable (RC/alpha/beta) candidate versions |
| `jar.gradle` | Includes `CHANGELOG.md` in `META-INF` and CycloneDX SBOM (`bom.json`) in published JAR |

## CI/CD Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci-draft.yml` | PR / push to main | Generates artefact version, updates spec version, builds, publishes draft to GitHub Packages + Azure Artifacts + SwaggerHub |
| `ci-released.yml` | GitHub Release published | Publishes release-tagged artefact |
| `lint-openapi.yml` | PR | Spectral lint; JSON schema lint (`jsonlint`); AJV schema-vs-example validation; rejects internal HMCTS domain URLs in the spec |
| `code-analysis.yml` | PR | PMD static analysis; SonarCloud |
| `codeql.yml` | PR + weekly | GitHub CodeQL security scan + CycloneDX SBOM |
| `secrets-scanner.yml` | PR + push | Secret scanning |
| `publish-openapi-spec.yml` | Called by ci-draft / ci-released | Publishes spec to SwaggerHub / APIHub |

CI injects the generated artefact version into `openapi-spec.yml` (via `hmcts/update-openapi-version`) before build steps run.

## Publishing

Artefacts publish to both:
- GitHub Packages: `maven.pkg.github.com/$GITHUB_REPOSITORY`
- Azure Artifacts: `pkgs.dev.azure.com/hmcts/Artifacts/_packaging/hmcts-lib/maven/v1`

Required env vars: `GITHUB_TOKEN`, `AZURE_DEVOPS_ARTIFACT_USERNAME`, `AZURE_DEVOPS_ARTIFACT_TOKEN`

Local publishing requires no credentials: `./gradlew publishToMavenLocal`

## Key Constraints

- **Java 25**, Spring Boot 4.0.x, **Jakarta EE** (not `javax`)
- `-Werror` — all compiler warnings fail the build; suppress explicitly or fix
- **OpenAPI 3.1.0** preferred for new specs; 3.0.0 still supported for existing
- **OpenAPI Generator**: target version 7.22.0 per upgrade cycle (versions 7.18.0–7.22.0 currently in use across repos)
- `@JsonInclude(NON_NULL)` **must** be present in `additionalModelTypeAnnotations` in `gradle/openapi.gradle` — prevents null fields appearing in JSON responses
- Do not reference internal HMCTS domains in the spec — CI (`lint-openapi.yml`) will reject: `cjscp.org.uk`, `service.gov.uk`, `justice.gov.uk`, `hmcts.net`, `ejudiciary.net`
- Test method names may use underscores — intentional, PMD ruleset permits this
- Run `/openapi-spec-reviewer` skill when authoring or reviewing the OpenAPI spec
