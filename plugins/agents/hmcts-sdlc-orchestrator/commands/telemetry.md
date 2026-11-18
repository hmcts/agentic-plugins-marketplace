---
description: Telemetry status, sign-in, opt-out
allowed-tools: Bash(python3 -B ${CLAUDE_PLUGIN_ROOT}/bin/cpp_telemetry:*)
argument-hint: status|login|optout|on|uninstall
---

Run this command with the Bash tool, then show the user its output exactly as printed, with nothing added:

```bash
python3 -B "${CLAUDE_PLUGIN_ROOT}/bin/cpp_telemetry" $ARGUMENTS
```

- With no argument, run it with `status`.
- For `login`, set the Bash timeout to 600000 ms. The command prints a sign-in code at once and then waits until the user has signed in in the browser.
- Do not run any other command.
