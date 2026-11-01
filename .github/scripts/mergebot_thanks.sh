#!/usr/bin/env bash
# Thank the author of the merged pull request, once: a welcome on a first contribution, kudos always.
# The team of the repository (admins, maintainers, writers) and the bots are not thanked.
# Environment: GH_TOKEN, REPO, PR.
set -euo pipefail

marker='<!-- mergebot-thanks -->'
if gh api "repos/$REPO/issues/$PR/comments" --paginate --jq '.[].body' | grep -qF "$marker"; then
    exit 0
fi

author=$(gh pr view "$PR" --repo "$REPO" --json author --jq '.author.login')
is_bot=$(gh pr view "$PR" --repo "$REPO" --json author --jq '.author.is_bot')
[ "$is_bot" = true ] && exit 0
role=$(gh api "repos/$REPO/collaborators/$author/permission" --jq '.role_name' 2>/dev/null || echo none)
case "$role" in
    admin|maintain|write) exit 0 ;;
esac

title=$(gh pr view "$PR" --repo "$REPO" --json title --jq '.title')
merged=$(gh api -X GET search/issues -f q="repo:$REPO is:pr is:merged author:$author" --jq '.total_count')

if [ "$merged" -le 1 ]; then
    body=$(cat <<EOF
:tada: Thank you @$author, your pull request is merged!

On behalf of the Odoo Mates team: welcome, and congratulations on your first contribution. **$title** is a great start, and we're looking forward to your next one. If you'd like to help further, have a look at the open [issues](https://github.com/$REPO/issues) and [Discussions](https://github.com/$REPO/discussions): we'd be happy to work with you again :raised_hands:

$marker
EOF
)
else
    body=$(cat <<EOF
:tada: Merged, thank you @$author!

That makes $merged of your pull requests merged at Odoo Mates: thank you for coming back.

Kudos for **$title** :clap:

$marker
EOF
)
fi
gh pr comment "$PR" --repo "$REPO" --body "$body" > /dev/null
