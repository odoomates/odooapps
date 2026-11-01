#!/usr/bin/env bash
# The mergebot: runs the command of a pull request comment (its first line, starting with /mergebot).
#   /mergebot r+                 merge the pull request (merge commit) once CI is green, then thank the author
#   /mergebot r+ minor|major|patch
#                               bump the version of the modules changed (not the new ones), then merge
#   /mergebot rebase             rebase the branch of the pull request on its target branch
#   /mergebot r-                 cancel a merge waiting for CI
# The bump and the rebase push to the branch of the pull request (often in a fork): they use
# MERGEBOT_TOKEN, a token of a maintainer, which also starts CI again on the new commits.
# Environment: GH_TOKEN, MERGEBOT_TOKEN, REPO, PR, ACTOR, COMMENT_ID, BODY, MERGEBOT_ROLES.
set -euo pipefail

scripts=$(dirname "$0")
read -r -a words <<< "$(printf '%s\n' "$BODY" | tr -d '\r' | grep -v '^[[:space:]]*$' | head -n 1 | tr '[:upper:]' '[:lower:]')"
[ "${words[0]:-}" = /mergebot ] || exit 0
level=""
case "${words[1]:-} ${words[2]:-}" in
    'r+ ') action=merge ;;
    'r+ major'|'r+ minor'|'r+ patch') action=merge; level=${words[2]} ;;
    'r- ') action=cancel ;;
    'rebase ') action=rebase ;;
    *) exit 0 ;;
esac

say() { gh pr comment "$PR" --repo "$REPO" --body "$1" > /dev/null; }

role=$(gh api "repos/$REPO/collaborators/$ACTOR/permission" --jq '.role_name' 2>/dev/null || echo none)
if ! printf ' %s ' "$MERGEBOT_ROLES" | grep -q " $role "; then
    say "@$ACTOR only the maintainers of the repository can use the mergebot."
    exit 0
fi
gh api -X POST "repos/$REPO/issues/comments/$COMMENT_ID/reactions" -f content=+1 > /dev/null

if [ "$action" = cancel ]; then
    gh pr merge "$PR" --repo "$REPO" --disable-auto > /dev/null 2>&1 || true
    say "Merge cancelled: the pull request will not be merged automatically."
    exit 0
fi

read -r state draft base head_repo head_branch head_sha merge_state node_id < <(gh pr view "$PR" --repo "$REPO" \
    --json state,isDraft,baseRefName,headRepositoryOwner,headRepository,headRefName,headRefOid,mergeStateStatus,id \
    --jq '"\(.state) \(.isDraft) \(.baseRefName) \(.headRepositoryOwner.login)/\(.headRepository.name) \(.headRefName) \(.headRefOid) \(.mergeStateStatus) \(.id)"')
if [ "$state" != OPEN ]; then
    say "This pull request is not open."
    exit 0
fi
if [ "$draft" = true ]; then
    say "This pull request is a draft: mark it ready for review first."
    exit 0
fi
if [ "$action" = rebase ] || [ -n "$level" ]; then
    if [ -z "${MERGEBOT_TOKEN:-}" ]; then
        say "The mergebot has no \`MERGEBOT_TOKEN\` secret to push to this branch: ask the author, or merge with \`/mergebot r+\`."
        exit 0
    fi
fi

# ---------------------------------------------------------------------------------------------------------
# rebase
# ---------------------------------------------------------------------------------------------------------
if [ "$action" = rebase ]; then
    # shellcheck disable=SC2016
    if GH_TOKEN=$MERGEBOT_TOKEN gh api graphql -f id="$node_id" -f oid="$head_sha" -f query='
        mutation($id: ID!, $oid: GitObjectID!) {
          updatePullRequestBranch(input: {pullRequestId: $id, expectedHeadOid: $oid, updateMethod: REBASE}) {
            pullRequest { headRefOid }
          }
        }' > /dev/null 2>&1; then
        say "Rebased on \`$base\`: CI runs again on the rebased commits."
    else
        say "The branch cannot be rebased automatically on \`$base\` (conflicts?): @$(gh pr view "$PR" --repo "$REPO" --json author --jq .author.login), please rebase it and force-push."
    fi
    exit 0
fi

# ---------------------------------------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------------------------------------
if [ "$merge_state" = DIRTY ]; then
    say "This pull request has conflicts with \`$base\`: \`/mergebot rebase\`, or ask the author to rebase it."
    exit 0
fi

bump_note=""
if [ -n "$level" ]; then
    work=$(mktemp -d)
    additions="$work/additions.jsonl"
    : > "$additions"
    bumped_modules=()
    for module in $(gh api "repos/$REPO/pulls/$PR/files" --paginate --jq '.[].filename' | grep / | cut -d/ -f1 | sort -u); do
        path="$module/__manifest__.py"
        # a new module keeps its version
        gh api "repos/$REPO/contents/$path?ref=$base" --jq .content 2>/dev/null | base64 -d > "$work/base" || continue
        [ -s "$work/base" ] || continue
        gh api "repos/$head_repo/contents/$path?ref=$head_sha" --jq .content 2>/dev/null | base64 -d > "$work/head" || continue
        [ -s "$work/head" ] || continue
        if python3 "$scripts/mergebot_version.py" "$level" "$work/base" < "$work/head" > "$work/new" 2> "$work/log"; then
            python3 -c 'import base64, json, sys; print(json.dumps({"path": sys.argv[1], "contents": base64.b64encode(open(sys.argv[2], "rb").read()).decode()}))' \
                "$path" "$work/new" >> "$additions"
            bumped_modules+=("$module $(cat "$work/log")")
        fi
    done
    if [ ! -s "$additions" ]; then
        bump_note=" No version to bump: new modules, or versions raised already."
    else
        names=$(printf '%s\n' "${bumped_modules[@]}" | cut -d' ' -f1 | paste -sd, | sed 's/,/, /g')
        python3 - "$additions" "$head_repo" "$head_branch" "$head_sha" "[REL] $names: $level version bump" > "$work/input.json" <<'EOF'
import json, sys
additions = [json.loads(line) for line in open(sys.argv[1])]
print(json.dumps({'input': {
    'branch': {'repositoryNameWithOwner': sys.argv[2], 'branchName': sys.argv[3]},
    'expectedHeadOid': sys.argv[4],
    'message': {'headline': sys.argv[5]},
    'fileChanges': {'additions': additions},
}}))
EOF
        # shellcheck disable=SC2016
        if ! GH_TOKEN=$MERGEBOT_TOKEN gh api graphql --input - > /dev/null 2> "$work/error" < <(python3 -c '
import json, sys
query = "mutation($input: CreateCommitOnBranchInput!) { createCommitOnBranch(input: $input) { commit { oid } } }"
print(json.dumps({"query": query, "variables": json.load(open(sys.argv[1]))}))' "$work/input.json"); then
            say "The version bump could not be pushed to the branch: $(head -c 300 "$work/error")"
            exit 0
        fi
        bump_note=" Version bump ($level): $(printf '%s; ' "${bumped_modules[@]}" | sed 's/; $//')."
        merge_state=PENDING
    fi
fi

behind=$(gh api "repos/$REPO/compare/$base...${head_repo%%/*}:$head_branch" --jq '.behind_by' 2>/dev/null || echo '?')
behind_note=""
if [ "$behind" != 0 ]; then
    behind_note=" The branch is $behind commit(s) behind \`$base\`."
fi

case "$merge_state" in
    CLEAN|HAS_HOOKS)
        gh pr merge "$PR" --repo "$REPO" --merge > /dev/null
        say "Merging now.$bump_note$behind_note" ;;
    *)
        gh pr merge "$PR" --repo "$REPO" --merge --auto > /dev/null
        say "Will merge as soon as CI is green.$bump_note$behind_note" ;;
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
bash "$scripts/mergebot_thanks.sh"
