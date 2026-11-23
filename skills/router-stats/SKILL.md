---
name: router-stats
description: Report frugal routing metrics - cost per agent tier and estimated savings versus running everything on the top-tier model.
disable-model-invocation: true
---

Run the report and show its output verbatim as markdown:

```
python3 "<plugin-root>/scripts/stats.py"
```

`<plugin-root>` is two directories up from this skill's base directory (the base directory is announced when this skill loads). Pass `--path <file>` only if the user names a different metrics file. An argument like `30d` or "last 30 days" maps to `--days 30`.

