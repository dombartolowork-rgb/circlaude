# Adding tools, and shipping updates

## Adding something

Three shapes, in order of how often you will want them.

**A skill** - one file, `skills/<name>/SKILL.md`, with YAML frontmatter
carrying `name` and `description`. No code. This is the right shape for an
agency *process*: how we open a job, how we build a budget, how we cost an
activation. The `description` is what makes Claude load it at the right
moment, so write it as the triggers someone would actually type.

**A command** - one file, `commands/<name>.md`, with a `description` in
frontmatter. A shortcut for something people run repeatedly. It usually just
points at a skill and fixes the order of steps.

**A CLI subcommand** - the only one that is real code. A module in
`lib/circle/<name>cmd.py` exposing `register(sub)`, plus one line in
`bin/circle`. Only needed when it has to talk to an API directly, the way
`mailcmd` and `teamwork` do. Python 3 stdlib only: no `pip install`, ever,
because the agency laptops are locked down.

After any change: `claude plugin validate .`

## Shipping an update

The mechanic that decides everything: **installing copies the plugin into a
version-pinned folder**, e.g.

```
~/.claude/plugins/cache/circlaude/circlaude/0.2.0
```

Note the version in the path. Editing this repo does nothing to anyone's
installed copy, and an update only reaches them **if the version number
changes**.

So a release is:

1. Make the change.
2. Bump `version` in **both** `.claude-plugin/plugin.json` and
   `.claude-plugin/marketplace.json`. They must agree, `claude plugin tag`
   validates that.
3. `claude plugin validate .`
4. Commit, then `claude plugin tag --push` to stamp `circlaude--v<version>`
   so there is a known-good release to roll back to.
5. Users run `/plugin update circlaude` and restart.

Semantic versioning is enough: patch for a fix, minor for a new skill or
command, major if someone's existing habit breaks.

## Why this wants to be hosted

While it ships as a zip or a local folder, every update means re-zipping,
re-uploading, re-sharing the link, and each person removing and re-adding the
marketplace. Versions drift and there is no way to know who is running what.

Hosted on git, you push and they run `/plugin update circlaude`. That is the
whole loop. It also gives a dated change history, which is the right answer
to "what does this tool do with our mail" when the AI policy question comes
up. GitHub or Azure DevOps, the plugin does not care.

## Listing it in the agency catalogue

There is a second, older marketplace named `circle-agency` at
`~/Documents/Subway/circle-tools`, holding `awd`, `subway-ingredients` and
`timesheet`. Cir'Claude should appear there too, as the agency's one
catalogue.

It cannot be wired up until this repo is hosted. A marketplace entry's
`source` must be either a path **inside** that repo or a git reference: an
absolute path is rejected, and a symlink pointing out of the repo is not
dereferenced at install. So the moment there is a remote, add this entry to
`circle-tools/.claude-plugin/marketplace.json` (verified to validate):

```json
{
  "name": "circlaude",
  "source": { "source": "github", "repo": "dombartolowork-rgb/circlaude" },
  "description": "Cir'Claude, the Circle Agency work assistant.",
  "version": "0.2.0",
  "category": "productivity",
  "strict": false
}
```

Anyone with both marketplaces added should install from **one** of them, not
both, or the skills and commands load twice.
