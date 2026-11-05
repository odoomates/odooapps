#!/usr/bin/env bash
# Forward-port a merged pull request (/mergebot r+ fw+): cherry-pick its commits on every higher version branch
# (16.0, 17.0, ... for a pull request merged into 15.0), up to the branch of its label fw-upto-<branch> if any, one
# pull request per branch. The merge commits are not
# ported; each branch gets its own version bump when its pull request is merged. The commits keep their
# message, the pull requests the description of the original and a reference to it, which lists them on it.
# The branches and the pull requests are made with MERGEBOT_TOKEN, a token of a maintainer, so that CI runs on
# them; a maintainer merges each one with /mergebot r+. On a branch where the commits do not apply, the conflicts are
# committed as they are, with their markers, in a draft pull request to finish by hand. Only git commands run on the
# code: nothing of the pull request is executed.
#
#   mergebot_forward_port.sh            forward-port the merged pull request PR
#   mergebot_forward_port.sh --targets  print the branches to forward-port to
#
# Environment: GH_TOKEN, MERGEBOT_TOKEN, REPO, PR (MERGEBOT_REMOTE: another git remote, for tests).
set -euo pipefail

say() { gh pr comment "$PR" --repo "$REPO" --body "$1" > /dev/null; }

base=$(gh pr view "$PR" --repo "$REPO" --json baseRefName --jq .baseRefName)
upto=$(gh pr view "$PR" --repo "$REPO" --json labels \
    --jq '.labels[].name | select(startswith("fw-upto-")) | ltrimstr("fw-upto-")' | head -n 1)
# the version branches (N.0) above the target branch and up to the last one, lowest first
targets=$(gh api "repos/$REPO/branches" --paginate --jq '.[].name' | grep -E '^[0-9]+\.0$' \
    | awk -F. -v base="${base%%.*}" -v upto="${upto%%.*}" '$1 + 0 > base + 0 && (upto == "" || $1 + 0 <= upto + 0)' \
    | sort -V || true)
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

title=$(gh pr view "$PR" --repo "$REPO" --json title --jq .title)
# a link to another repository is about this pull request, not about its forward-ports
description=$(gh pr view "$PR" --repo "$REPO" --json body --jq .body | tr -d '\r' \
    | { grep -viE '^[[:space:]]*linked:[[:space:]]*[^[:space:]]+#[0-9]+[[:space:]]*$' || true; })
mapfile -t commits < <(gh api "repos/$REPO/pulls/$PR/commits" --paginate --jq '.[]
    | select((.parents | length) == 1)
    | .sha')
if [ ${#commits[@]} -eq 0 ]; then
    say "No forward-port: the pull request has no commit to port.
$marker"
    exit 0
fi

fw_description="${description:+$description

}Forward-port of #$PR: ${commits[*]}"

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
drafts=0
for target in $targets; do
    branch="$target-fw-$PR"
    if gh api "repos/$REPO/branches/$branch" > /dev/null 2>&1; then
        opened+=("- \`$target\`: branch \`$branch\` exists already")
        continue
    fi
    git -C "$work" fetch -q --filter=blob:none origin "$target"
    git -C "$work" checkout -q -B "$branch" FETCH_HEAD
    conflicts=()
    for commit in "${commits[@]}"; do
        if git -C "$work" cherry-pick --allow-empty --keep-redundant-commits "$commit" > /dev/null 2>&1; then
            continue
        fi
        conflicts+=("- \`${commit:0:8}\` $(git -C "$work" log -1 --format=%s "$commit"): $(git -C "$work" diff --name-only \
            --diff-filter=U | sed 's/.*/`&`/' | paste -sd' ' -)")
        git -C "$work" add -A
        git -C "$work" -c core.editor=true commit -q --no-edit --allow-empty
    done
    if git -C "$work" diff --quiet FETCH_HEAD HEAD; then
        opened+=("- \`$target\`: nothing to port, the change is there already")
        continue
    fi
    git -C "$work" push -q origin "$branch"
    if [ ${#conflicts[@]} -eq 0 ]; then
        url=$(GH_TOKEN=$MERGEBOT_TOKEN gh pr create --repo "$REPO" --base "$target" --head "$branch" \
            --title "[FW $target] $title" --body "$fw_description")
        opened+=("- \`$target\`: $url")
    else
        conflict_list=$(printf '%s\n' "${conflicts[@]}")
        url=$(GH_TOKEN=$MERGEBOT_TOKEN gh pr create --repo "$REPO" --base "$target" --head "$branch" --draft \
            --title "[FW $target] $title" --body "$fw_description

**Conflicts to resolve.** These commits did not apply and are committed with their conflict markers:

$conflict_list")
        opened+=("- \`$target\`: $url (draft: conflicts to resolve)")
        drafts=$((drafts + 1))
    fi
done

body="Forward-port of this pull request:
$(printf '%s\n' "${opened[@]}")"
if [ "$drafts" -gt 0 ]; then
    body="$body

A draft holds conflict markers: resolve them, push, then mark it ready for review."
fi
say "$body
$marker"
