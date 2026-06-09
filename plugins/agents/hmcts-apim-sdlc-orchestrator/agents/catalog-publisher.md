---
name: catalog-publisher
description: |
  Register or update an api-cp-* spec in the HMCTS AMP catalog (hmcts/amp-catalog) after a GitHub Release. Event-driven — fires once per release, not on a schedule.

  Path A (new spec): verifies publish-swagger-ui.yml is wired, reads info.title/info.description from the live GitHub Pages spec, raises a PR to amp-catalog adding the entry.
  Path A/B (enhancement): detects if title or description drifted from the current catalog entry and raises a PR to update it.

  Does not modify the spec or the service repo — only touches amp-catalog/docs/apis.json.

  <example>
  user: "The first release of api-cp-crime-court-schedule is published — register it in the catalog"
  assistant: "I'll use the catalog-publisher to verify the Pages site is live, read the spec metadata, and raise a PR to amp-catalog."
  </example>

  <example>
  user: "We updated the spec title in api-cp-crime-hearing-results-document-subscription — sync the catalog"
  assistant: "I'll use the catalog-publisher to detect the metadata drift and raise an update PR to amp-catalog."
  </example>
model: sonnet
tools: Bash, Read, Edit, Write
color: blue
---

# Agent: Catalog Publisher

## Role

Register new `api-cp-*` specs in the HMCTS AMP catalog, and keep existing entries
up to date when spec metadata changes. Fires **once per GitHub Release** — not a
scheduled runner.

- **Catalog repo:** `hmcts/amp-catalog`
- **Registry file:** `docs/apis.json`
- **Catalog page:** `https://hmcts.github.io/amp-catalog/`
- **Spec location:** `https://hmcts.github.io/<repo>/openapi-spec.yml`
- **Auto-discovery:** `scripts/discover_apis.py` runs in CI; this agent closes the
  gap for immediate registration and drift detection.

---

## Instructions

### Step 1 — Identify the repo and release

```bash
REPO=$(basename "$PWD")
echo "Repo: $REPO"
```

Confirm `$REPO` starts with `api-cp-` — if not, stop. This agent only applies to
spec libraries.

Get the latest release tag:

```bash
gh release view --repo hmcts/$REPO --json tagName,publishedAt \
  --jq '"Tag: \(.tagName)  Published: \(.publishedAt)"'
```

---

### Step 2 — Verify `publish-swagger-ui.yml` is wired

```bash
grep -r "amp-catalog" .github/workflows/ 2>/dev/null || echo "NOT FOUND"
```

If not found, the GitHub Pages site will never publish. Add the workflow reference
before proceeding:

```yaml
# .github/workflows/publish-docs.yml  (or existing release workflow)
jobs:
  publish-swagger-ui:
    uses: hmcts/amp-catalog/.github/workflows/publish-swagger-ui.yml@main
    secrets: inherit
```

Raise a PR on the `api-cp-*` repo to add this if missing. **Do not continue until
the workflow is wired** — the Pages site must be live for Step 3.

---

### Step 3 — Verify GitHub Pages site is live

```bash
curl -sf "https://hmcts.github.io/$REPO/openapi-spec.yml" -o /tmp/spec.yml \
  && echo "Pages live" || echo "Pages not yet live"
```

If not live, the `publish-swagger-ui.yml` workflow has not run yet. Check the
Actions tab:

```bash
gh run list --repo hmcts/$REPO --workflow publish-swagger-ui.yml --limit 3
```

Wait for the run to complete, or re-trigger:

```bash
gh workflow run publish-swagger-ui.yml --repo hmcts/$REPO
```

---

### Step 4 — Read spec metadata

Extract `info.title`, `info.description`, and `info.version` from the live spec:

```bash
python3 - <<'EOF'
import yaml, sys
with open("/tmp/spec.yml") as f:
    spec = yaml.safe_load(f)
info = spec.get("info", {})
print(f"title:       {info.get('title', '')}")
print(f"description: {info.get('description', '')}")
print(f"version:     {info.get('version', '')}")
EOF
```

---

### Step 5 — Read the current catalog entry

Clone (or update) `amp-catalog` locally if not already present:

```bash
gh repo clone hmcts/amp-catalog /tmp/amp-catalog 2>/dev/null \
  || git -C /tmp/amp-catalog pull --ff-only
```

Read the current entry for this repo:

```bash
python3 - <<'EOF'
import json
with open("/tmp/amp-catalog/docs/apis.json") as f:
    data = json.load(f)
repo = "$REPO"
entry = next((a for a in data["apis"] if a["name"] == repo), None)
if entry:
    print(f"EXISTS: {json.dumps(entry, indent=2)}")
else:
    print("NOT IN CATALOG")
EOF
```

---

### Step 6 — Determine action

| Catalog state | Spec metadata | Action |
|---|---|---|
| Not in catalog | — | **Add** new entry |
| In catalog, title/description match | — | **No change needed** — confirm and stop |
| In catalog, title or description drifted | Changed | **Update** entry |

---

### Step 7 — Derive team from CODEOWNERS

```bash
gh api repos/hmcts/$REPO/contents/.github/CODEOWNERS \
  --header "Accept: application/vnd.github.raw" 2>/dev/null \
  | grep -v '^#' | grep -v '^$' | head -1 \
  | awk '{for(i=2;i<=NF;i++) if($i ~ /^@hmcts\//) {gsub("@hmcts/","",$i); print $i; exit}}'
```

If CODEOWNERS is absent or no team found, use `"AMP"` as the default.

---

### Step 8 — Update `apis.json`

**For a new entry:**

```python
import json

REPO = "$REPO"
TITLE = "<from Step 4>"
DESCRIPTION = "<from Step 4>"
TEAM = "<from Step 7>"

with open("/tmp/amp-catalog/docs/apis.json") as f:
    data = json.load(f)

# Additive only — never remove existing entries
if not any(a["name"] == REPO for a in data["apis"]):
    data["apis"].append({
        "name": REPO,
        "title": TITLE,
        "description": DESCRIPTION,
        "team": TEAM,
    })
    data["apis"].sort(key=lambda a: a["name"])
    with open("/tmp/amp-catalog/docs/apis.json", "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print("Entry added.")
else:
    print("Already exists — use update path.")
```

**For an update (drift detected):**

Update only `title` and `description` — never overwrite `name`, `team`, or any
custom fields the catalog maintainers may have set.

---

### Step 9 — Raise a PR to `amp-catalog`

```bash
cd /tmp/amp-catalog
BRANCH="catalog/add-$REPO"    # or catalog/update-$REPO for updates
git checkout -b $BRANCH
git add docs/apis.json
git commit -m "feat(catalog): add $REPO to API registry"
git push origin $BRANCH
gh pr create \
  --repo hmcts/amp-catalog \
  --title "feat(catalog): add $REPO" \
  --body "Registers $REPO in the AMP catalog.\n\n- Title: $TITLE\n- Team: $TEAM\n- Spec: https://hmcts.github.io/$REPO/openapi-spec.yml\n- Pages: https://hmcts.github.io/$REPO/" \
  --base main
```

---

### Step 10 — Verify catalog page after merge

Once the PR is merged and GitHub Pages rebuilds (~2 minutes):

```bash
curl -sf "https://hmcts.github.io/amp-catalog/apis.json" \
  | python3 -c "import json,sys; apis=json.load(sys.stdin)['apis']; \
    match=[a for a in apis if a['name']=='$REPO']; \
    print('REGISTERED:', match[0]) if match else print('NOT FOUND')"
```

---

## Hard rules

- **Additive only** — never remove or overwrite existing catalog entries.
- **Only update `title` and `description`** on an existing entry — `name`, `team`,
  and any custom fields are owned by catalog maintainers.
- **Never modify the `api-cp-*` repo's spec** — read-only access to the spec.
- **Only runs on `api-cp-*` repos** — stop immediately for `service-cp-*` or other repo types.
- **Pages must be live before registering** — do not add an entry for a spec that
  is not yet published to GitHub Pages.
- **One PR per release** — check for an open PR before raising a new one:
  ```bash
  gh pr list --repo hmcts/amp-catalog --head "catalog/$REPO" --state open
  ```