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
  version.
- The summary line is at most 50 characters, in English, without a full stop.
  For example: `[FIX] om_account_followup: level of paid invoices`.
- Add a body after a blank line only when the why is not obvious from the
  summary.
- Use `*` as the module when one change touches several modules:
  `[I18N] *: Spanish translations`.

### Review

A maintainer reviews the pull request. Answer the comments and push the
corrections to the same branch. A pull request without an answer for 30 days may
be closed.

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
