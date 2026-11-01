#!/usr/bin/env bash
# Thank the author of the merged pull request, once: a welcome for a first contribution, kudos always.
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
    thanks="Welcome to the contributors of Odoo Apps: this is your first merged pull request here, and we hope the first of many."
else
    thanks="That makes $merged pull requests of yours merged here: thank you for coming back!"
fi

body=$(cat <<EOF
:tada: Merged, thank you @$author!

$thanks Kudos for **$title**: it is on the \`$(gh pr view "$PR" --repo "$REPO" --json baseRefName --jq .baseRefName)\` branch now, and reaches the users with the next update of the module on the Odoo Apps store.

$marker
EOF
)
gh pr comment "$PR" --repo "$REPO" --body "$body" > /dev/null
