# Contributing to Odoo Mates apps

Thank you for helping. Bug reports, fixes, translations and documentation are all
welcome. Please read this page first: it saves time for you and for the
maintainers.

By taking part you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

- [Branches and versions](#branches-and-versions)
- [How to report a bug](#how-to-report-a-bug)
- [How to suggest a feature](#how-to-suggest-a-feature)
- [How to send a pull request](#how-to-send-a-pull-request)
- [Translations](#translations)
- [AI tools](#ai-tools)
- [License](#license)

## Branches and versions

Each Odoo version has its own branch: `20.0`, `19.0`, `18.0`… The default branch
is the newest version.

| Version | Bug fixes | New features |
|---------|-----------|--------------|
| 20.0    | ✅ | ✅ |
| 19.0    | ✅ | case by case |
| 18.0    | ✅ | case by case |
| 17.0 and older | ❌ | ❌ |

## How to report a bug

1. **Search first.** Look through the
   [open and closed issues](https://github.com/odoomates/odooapps/issues?q=is%3Aissue):
   the bug may already be known or fixed.
2. **Update.** Pull the latest commit of your branch, upgrade the module
   (`-u <module>`) and try again.
3. **Check where it comes from.** Try with only Odoo and the module installed. If
   it also happens without the module, it is a problem of Odoo or of another
   module, not of this repository.
4. **Open a [bug report](https://github.com/odoomates/odooapps/issues/new/choose)**
   and fill in the form:
   - the module and the Odoo version (branch);
   - the steps to reproduce, from a fresh database if you can (with or without
     demo data);
   - what you expected, and what happened instead;
   - the **full error and traceback**, as text, not as a screenshot. Find it in
     the error dialog (*Copy the full error to clipboard*) or in the server log;
   - screenshots, when the problem is in the screen or in a report.

**One issue for one problem.** Write in English if you can. Remove any customer
data, password or token from the logs and screenshots.

**Security problems are never reported in an issue:** follow
[SECURITY.md](SECURITY.md).

Questions on how to use or configure a module ("how do I…?") go to
[Discussions](https://github.com/odoomates/odooapps/discussions), not to issues.

## How to suggest a feature

Open a [feature request](https://github.com/odoomates/odooapps/issues/new/choose).
Explain the business need first (what you are trying to do, and why), then the
solution you have in mind. A feature request is not a promise: it is
weighed against how many users need it and how much it costs to maintain.

## How to send a pull request

For anything bigger than a small fix, **open an issue first** and agree on the
approach. This avoids work that cannot be merged.

### Steps

1. Fork the repository and create a branch from the version branch you fix,
   for example `20.0-fix-followup-email`.
2. Make the change. Fix a bug on the oldest supported version that has it, and
   say in the pull request which newer versions need the same fix.
3. Add or update the tests (`tests/` of the module) and run them:

   ```bash
   odoo-bin -d test_db -i <module> --test-tags /<module> --stop-after-init
   ```

4. Open the pull request against the same version branch, and fill in the
   template.

### Code

- Follow the [Odoo coding guidelines](https://www.odoo.com/documentation/master/contributing/development/coding_guidelines.html)
  and the style of the module you change.
- Keep the change focused: no unrelated reformatting, no renamed files or
  fields "while you are there".
- Every user-facing text is translatable: `_()` / `self.env._()` in Python,
  plain text in XML.
- Changes to the data model of a released module need a migration script in
  `migrations/<version>/`, and a higher `version` in `__manifest__.py`.
- New features need a few lines in the description page of the module
  (`static/description/index.html`).

### Commits

One commit per module and per logical change, written as in Odoo:

```text
[TAG] module: short summary of the change
```

- **Tags:** `[FIX]` bug fix, `[IMP]` improvement, `[ADD]` new module, `[REM]`
  removal, `[REF]` refactoring, `[I18N]` translations, `[MIG]` migration to a new
  version; and, as in Odoo, `[REV]` revert, `[MOV]` move, `[REL]` release,
  `[MERGE]` merge, `[CLA]` contributor agreement, `[PERF]` performance, `[CLN]`
  clean-up, `[LINT]` linting.
- The summary after `module: ` is at most 50 characters, in English, without a
  full stop. For example: `[FIX] om_account_followup: level of paid invoices`.
- Add a body after a blank line only when the why is not obvious from the
  summary.
- Use `*` as the module when one change touches several modules:
  `[I18N] *: Spanish translations`.

CI checks the first line of every commit of a pull request (merge commits
aside): the *commit messages* check fails and lists the commits to fix. Reword
them with `git rebase -i` and force-push your branch.

The *odoo guidelines* check reads the lines you add: a debugger, a `print`, or the
version of another branch in a manifest fail, and it warns about `cr.commit()` and
SQL built from strings.

### Review

A maintainer reviews the pull request. Answer the comments and push the
corrections to the same branch. A pull request without an answer for 30 days may
be closed.

### Merging

Pull requests are rebased onto the version branch, without a merge commit: your
commits come into the branch one after the other, under your name. Before the
merge, a maintainer may ask you to:

- **rebase** your branch on the current version branch (`20.0`...), when it is
  much older;
- **squash** your commits, when there are several small ones ("fix typo",
  "review") that belong to one change.

The maintainers merge with the mergebot, by a comment on the pull request whose
first line is the command (with its slash):

- `/mergebot r+` merges it as soon as CI is green; if your branch is behind the
  version branch, it is rebased first and CI runs again on the rebased commits
  before the merge. Once merged, the mergebot raises the patch version of the
  modules it changes, in one `[BOT] post-merge updates` commit on the version branch. A new module,
  or one whose version your pull request changes, keeps its version;
- `/mergebot r+ minor` (or `major`) does the same with a minor or major version;
- `/mergebot r+ nobump` does the same without raising the version;
- `/mergebot r+ skipci` merges it now, without waiting for CI: only for an admin of
  the repository, when a failing check has nothing to do with the change;
- `/mergebot rebase` rebases your branch on the version branch;
- `/mergebot squash` makes your commits one commit, with the message of the first one;
- `/mergebot r+ fw+` merges it, then forward-ports it: the mergebot
  cherry-picks its commits on every higher version branch (for 15.0: 16.0 to
  20.0) and opens one pull request per branch; each one is merged by a maintainer
  with `/mergebot r+` once its CI is green;
- `/mergebot r+ fw+ 19.0` (or `fw+ upto 19.0`) forward-ports it up to that branch
  included: for a module not on the higher branches, or a fix they do not need;
- `/mergebot r-` cancels a merge waiting for CI, or for a linked pull request.

A pull request that goes with one in another repository says so with a line in its
description: `Linked: owner/repo#12`. `/mergebot r+` then waits for `/mergebot r+`
on the other one, and the second one merges both.

A wrong command is declined with a comment, and nothing is done. Once merged, the
mergebot thanks you on the pull request.

## Translations

Translations are the `i18n/<lang>.po` files of each module, made from the
`i18n/<module>.pot` template.

- To improve a translation, edit the `.po` file and send a pull request with an
  `[I18N]` commit.
- To add a language, copy the `.pot` file to `i18n/<lang>.po` (for example
  `fr.po`) and translate it.
- Don't edit the `.pot` file by hand: it is exported from Odoo when the module
  changes.

## AI tools

You may use AI tools to help you, but you remain responsible for everything you
submit. Read the [AI contribution policy](AI_POLICY.md) before you do.

## License

The modules are published under the
[GNU LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html) license, as declared
in the `__manifest__.py` of each module. By sending a contribution, you agree
that it is published under the same license.
