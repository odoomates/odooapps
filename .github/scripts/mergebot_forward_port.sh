#!/usr/bin/env bash
# Forward-port a merged pull request (/mergebot r+ fw+): cherry-pick its commits on every higher version branch
# (16.0, 17.0, ... for a pull request merged into 15.0), one pull request per branch. The version bumps of the
# mergebot ("[REL] ...: <level> version bump") and the merge commits are not ported.
# The branches and the pull requests are made with MERGEBOT_TOKEN, a token of a maintainer, so that CI runs on
# them; a maintainer merges each one with /mergebot r+. A branch where the commits do not apply is listed in a
# comment, to port by hand. Only git commands run on the code: nothing of the pull request is executed.
#
#   mergebot_forward_port.sh            forward-port the merged pull request PR
#   mergebot_forward_port.sh --targets  print the higher version branches of the target branch of PR
#
# Environment: GH_TOKEN, MERGEBOT_TOKEN, REPO, PR (MERGEBOT_REMOTE: another git remote, for tests).
set -euo pipefail

say() { gh pr comment "$PR" --repo "$REPO" --body "$1" > /dev/null; }

base=$(gh pr view "$PR" --repo "$REPO" --json baseRefName --jq .baseRefName)
# the version branches (N.0) above the target branch, lowest first
targets=$(gh api "repos/$REPO/branches" --paginate --jq '.[].name' | grep -E '^[0-9]+\.0$' \
    | awk -F. -v base="${base%%.*}" '$1 + 0 > base + 0' | sort -V || true)
if [ "${1:-}" = --targets ]; then
    [[ $base =~ ^[0-9]+\.0$ ]] && printf '%s\n' "$targets" | grep . || true
    exit 0
fi

marker='<!-- mergebot-forward-port -->'
if gh api "repos/$REPO/issues/$PR/comments" --paginate --jq '.[].body' | grep -qF "$marker"; then
    exit 0
fi
if ! [[ $base =~ ^[0-9]+\.0$ ]] || [ -z "$targets" ]; then
    say "No forward-port: \`$base\` has no higher version branch.
$marker"
    exit 0
fi
if [ -z "${MERGEBOT_TOKEN:-}" ]; then
    say "No forward-port: the mergebot has no \`MERGEBOT_TOKEN\` secret to push the branches.
$marker"
    exit 0
fi

author=$(gh pr view "$PR" --repo "$REPO" --json author --jq .author.login)
title=$(gh pr view "$PR" --repo "$REPO" --json title --jq .title)
mapfile -t commits < <(gh api "repos/$REPO/pulls/$PR/commits" --paginate --jq '.[]
    | select((.parents | length) == 1)
    | select(.commit.message | test("^\\[REL\\] [^\n]*: (major|minor|patch) version bump") | not)
    | .sha')
if [ ${#commits[@]} -eq 0 ]; then
    say "No forward-port: the pull request has no commit to port.
$marker"
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git -C "$work" init -q
git -C "$work" config user.name mergebot
git -C "$work" config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git -C "$work" config http.https://github.com/.extraheader \
    "AUTHORIZATION: basic $(printf 'x-access-token:%s' "$MERGEBOT_TOKEN" | base64 -w0)"
git -C "$work" remote add origin "${MERGEBOT_REMOTE:-https://github.com/$REPO.git}"
git -C "$work" fetch -q --filter=blob:none origin "refs/pull/$PR/head"

opened=()
failed=()
for target in $targets; do
    branch="$target-fw-$PR"
    if gh api "repos/$REPO/branches/$branch" > /dev/null 2>&1; then
        opened+=("- \`$target\`: branch \`$branch\` exists already")
        continue
    fi
    git -C "$work" fetch -q --filter=blob:none origin "$target"
    git -C "$work" checkout -q -B "$branch" FETCH_HEAD
    if ! git -C "$work" cherry-pick -x --allow-empty --keep-redundant-commits "${commits[@]}" > /dev/null 2>&1; then
        git -C "$work" cherry-pick --abort > /dev/null 2>&1 || true
        failed+=("$target")
        continue
    fi
    if git -C "$work" diff --quiet FETCH_HEAD HEAD; then
        opened+=("- \`$target\`: nothing to port, the change is there already")
        continue
    fi
    git -C "$work" push -q origin "$branch"
    url=$(GH_TOKEN=$MERGEBOT_TOKEN gh pr create --repo "$REPO" --base "$target" --head "$branch" \
        --title "[FW $target] $title" --body "Forward-port of #$PR (merged into \`$base\`) to \`$target\`, by the mergebot: its commits, cherry-picked. Thank you @$author!

CI runs on this pull request: a maintainer reviews it (the API may differ on \`$target\`) and merges it with \`/mergebot r+\`.")
    opened+=("- \`$target\`: $url")
done

body="Forward-port of this pull request:
$(printf '%s\n' "${opened[@]}")"
if [ ${#failed[@]} -gt 0 ]; then
    body="$body
$(for target in "${failed[@]}"; do printf -- '- `%s`: the commits do not apply (conflicts), to port by hand\n' "$target"; done)

To port by hand, for each of these branches (\`<branch>\` = $(printf '`%s` ' "${failed[@]}" | sed 's/ $//')):
\`\`\`
git fetch origin <branch> pull/$PR/head
git checkout -b <branch>-fw-$PR origin/<branch>
git cherry-pick -x ${commits[*]}
\`\`\`
then open a pull request to \`<branch>\`."
fi
say "$body
$marker"
