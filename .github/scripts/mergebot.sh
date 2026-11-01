#!/usr/bin/env bash
# The mergebot: runs the command of a pull request comment.
#   mergebot r+   merge the pull request (merge commit) once CI is green, then thank the author
#   mergebot r-   cancel a merge waiting for CI
# Environment: GH_TOKEN, REPO, PR, ACTOR, COMMENT_ID, BODY, MERGEBOT_ROLES.
set -euo pipefail

command=$(printf '%s\n' "$BODY" | head -n 1 | tr -d '\r' | tr '[:upper:]' '[:lower:]' | xargs)
case "$command" in
    'mergebot r+') action=merge ;;
    'mergebot r-') action=cancel ;;
    *) exit 0 ;;
esac

say() { gh pr comment "$PR" --repo "$REPO" --body "$1" > /dev/null; }

role=$(gh api "repos/$REPO/collaborators/$ACTOR/permission" --jq '.role_name' 2>/dev/null || echo none)
if ! printf ' %s ' "$MERGEBOT_ROLES" | grep -q " $role "; then
    say "@$ACTOR only the maintainers of the repository can merge with the mergebot."
    exit 0
fi
gh api -X POST "repos/$REPO/issues/comments/$COMMENT_ID/reactions" -f content=+1 > /dev/null

if [ "$action" = cancel ]; then
    gh pr merge "$PR" --repo "$REPO" --disable-auto > /dev/null 2>&1 || true
    say "Merge cancelled: the pull request will not be merged automatically."
    exit 0
fi

read -r state draft base head_label merge_state < <(gh pr view "$PR" --repo "$REPO" \
    --json state,isDraft,baseRefName,headRepositoryOwner,headRefName,mergeStateStatus \
    --jq '"\(.state) \(.isDraft) \(.baseRefName) \(.headRepositoryOwner.login):\(.headRefName) \(.mergeStateStatus)"')
if [ "$state" != OPEN ]; then
    say "This pull request is not open: nothing to merge."
    exit 0
fi
if [ "$draft" = true ]; then
    say "This pull request is a draft: mark it ready for review first."
    exit 0
fi
behind=$(gh api "repos/$REPO/compare/$base...$head_label" --jq '.behind_by' 2>/dev/null || echo '?')
behind_note=""
if [ "$behind" != 0 ]; then
    behind_note=" The branch is $behind commit(s) behind \`$base\`."
fi

case "$merge_state" in
    DIRTY)
        say "This pull request has conflicts with \`$base\`: please rebase it, then ask again."
        exit 0 ;;
    CLEAN|HAS_HOOKS)
        gh pr merge "$PR" --repo "$REPO" --merge > /dev/null
        say "Merging now.$behind_note" ;;
    *)
        gh pr merge "$PR" --repo "$REPO" --merge --auto > /dev/null
        say "Will merge as soon as CI is green.$behind_note" ;;
esac

# follow the merge (CI may take a while), to thank the author once it is done
for _ in $(seq 1 140); do
    state=$(gh pr view "$PR" --repo "$REPO" --json state --jq .state)
    [ "$state" = MERGED ] && break
    [ "$state" = CLOSED ] && exit 0
    waiting=$(gh pr view "$PR" --repo "$REPO" --json autoMergeRequest --jq '.autoMergeRequest != null')
    # the merge was cancelled, or CI failed
    [ "$waiting" = false ] && exit 0
    sleep 60
done
[ "$state" = MERGED ] || exit 0
bash "$(dirname "$0")/mergebot_thanks.sh"
