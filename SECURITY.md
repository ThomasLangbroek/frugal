# Security policy

## Supported versions

The latest release only.

## Reporting

Use GitHub private vulnerability reporting (Security tab → Report a
vulnerability). Please do not open public issues for exploitable problems.

## Scope worth knowing

Frugal's hooks execute as shell commands on the user's machine via Claude
Code's hook mechanism, with the user's permissions. They are fail-open by
design: a parse error must allow the action rather than break the session.
Anything that lets crafted hook input execute unintended commands, write
outside the metrics file, or silently disable the fail-open behaviour is in
scope and taken seriously. Cost-routing bugs (wrong tier, wrong price) are
ordinary bugs, not security issues.
