---
name: models
description: Show or change which model each frugal agent runs on, per project. Use when the user wants to see the current tier-to-model mapping, move an agent to a different model (e.g. scout to sonnet), or reset overrides. Triggers on "frugal models", "change router models", "which model does scout use".
disable-model-invocation: true
---

# Frugal model overrides

Manage the per-project model mapping for frugal's agents. Defaults live in each
agent's frontmatter (`agents/*.md` under the plugin root); overrides live in the
project's `.claude/routing-overrides.md`, which the routing policy reads first.
Overrides work because the Agent tool accepts a `model` parameter per spawn - no
plugin files are ever edited.

Valid agents: `scout`, `extractor`, `mechanic`, `builder`, `sage`.
Valid models: `haiku`, `sonnet`, `opus`, `fable`.

## No arguments: show the mapping

1. Read each agent's default from the `model:` frontmatter line in
   `<plugin-root>/agents/*.md` (plugin root is two directories up from this
   skill's base directory).
2. Read the "Model overrides" section of `.claude/routing-overrides.md` if it
   exists.
3. Show one table: agent, default, override (or "-"), effective model. Nothing
   else.

## Arguments like `scout=sonnet builder=opus`

1. Validate every pair against the lists above. Invalid agent or model: reject
   with the valid options, change nothing.
2. Create or update the managed section in `.claude/routing-overrides.md`
   (create the file if missing, keep any unmanaged content above it intact):

   ```markdown
   ## Model overrides (managed by /frugal:models)

   | Agent | Model |
   |---|---|
   | scout | sonnet |

   When spawning a frugal agent listed above, pass its listed model as the
   Agent tool's `model` parameter.
   ```

3. Merge with existing overrides: new pairs win, unmentioned pairs stay.
4. Setting an agent to its default removes its row. Empty table: remove the
   whole section.
5. Confirm with the resulting mapping table and apply it immediately to any
   spawns later in this session.

## Argument `reset`

Remove the managed section. If the file is then empty, delete the file.
Show the default mapping.
