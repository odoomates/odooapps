#!/usr/bin/env bash
# The mergebot: runs the command of a pull request comment (its first line, starting with /mergebot).
#   /mergebot r+                 merge the pull request (a merge commit "Merge PR #N into <branch>", the commits of
#                               the author unchanged) once CI is green, then thank the author;
#                               a branch behind its target branch is rebased first, and CI runs again on the rebased
#                               commits before the merge
#   /mergebot r+ minor|major|patch
#                               bump the version of the modules changed (not the new ones), then merge
#   /mergebot r+ fw+             merge, then forward-port: one pull request of its commits to every higher version
#                               branch (fw+ goes with r+, in any order, also with a bump level)
#   /mergebot rebase             rebase the branch of the pull request on its target branch
#   /mergebot r-                 cancel a merge waiting for CI (and its forward-port)
# The bump and the rebases push to the branch of the pull request (often in a fork): they use
# MERGEBOT_TOKEN, a token of a maintainer, which also starts CI again on the new commits.
# Environment: GH_TOKEN, MERGEBOT_TOKEN, REPO, PR, ACTOR, COMMENT_ID, BODY, MERGEBOT_ROLES.
set -euo pipefail

scripts=$(dirname "$0")
read -r -a words <<< "$(printf '%s\n' "$BODY" | tr -d '\r' | grep -v '^[[:space:]]*$' | head -n 1 | tr '[:upper:]' '[:lower:]')"
[ "${words[0]:-}" = /mergebot ] || exit 0
action=""
level=""
forward=false
for word in "${words[@]:1}"; do
    case "$word" in
        r+) action=merge ;;
        r-) action=cancel ;;
        rebase) action=rebase ;;
        major|minor|patch) level=$word ;;
        fw+) forward=true ;;
        *) exit 0 ;;
    esac
done
[ -n "$action" ] || [ "$forward" = true ] || exit 0
fw_label=forward-port

say() { gh pr comment "$PR" --repo "$REPO" --body "$1" > /dev/null; }

# rebase the branch of the pull request (head $1) on its target branch, with the token of a maintainer: it also
# starts CI again on the new commits
rebase_branch() {
    # shellcheck disable=SC2016
    GH_TOKEN=$MERGEBOT_TOKEN gh api graphql -f id="$node_id" -f oid="$1" -f query='
        mutation($id: ID!, $oid: GitObjectID!) {
          updatePullRequestBranch(input: {pullRequestId: $id, expectedHeadOid: $oid, updateMethod: REBASE}) {
            pullRequest { headRefOid }
          }
        }' > /dev/null 2>&1
}

# the number of commits of the target branch missing from the branch of the pull request ('?' if unknown)
commits_behind() {
    gh api "repos/$REPO/compare/$base...${head_repo%%/*}:$head_branch" --jq '.behind_by' 2>/dev/null || echo '?'
}

role=$(gh api "repos/$REPO/collaborators/$ACTOR/permission" --jq '.role_name' 2>/dev/null || echo none)
if ! printf ' %s ' "$MERGEBOT_ROLES" | grep -q " $role "; then
    say "@$ACTOR only the maintainers of the repository can use the mergebot."
    exit 0
fi
if [ "$action" != merge ] && { [ -n "$level" ] || [ "$forward" = true ]; }; then
    say "\`fw+\` and the bump levels go with \`r+\`: \`/mergebot r+ fw+\`, \`/mergebot r+ minor fw+\`."
    exit 0
fi
gh api -X POST "repos/$REPO/issues/comments/$COMMENT_ID/reactions" -f content=+1 > /dev/null

if [ "$action" = cancel ]; then
    gh pr merge "$PR" --repo "$REPO" --disable-auto > /dev/null 2>&1 || true
    gh pr edit "$PR" --repo "$REPO" --remove-label "$fw_label" > /dev/null 2>&1 || true
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

# fw+: the higher version branches to forward-port to, remembered with a label (also for a merge by hand)
fw_note=""
if [ "$forward" = true ]; then
    if [[ $head_branch =~ ^[0-9]+\.0-fw-[0-9]+$ ]]; then
        say "This pull request is a forward-port already: merge it with \`/mergebot r+\` (without \`fw+\`)."
        exit 0
    fi
    if [ -z "${MERGEBOT_TOKEN:-}" ]; then
        say "The mergebot has no \`MERGEBOT_TOKEN\` secret to push the forward-ports: \`/mergebot r+\` without \`fw+\`."
        exit 0
    fi
    fw_targets=$(bash "$scripts/mergebot_forward_port.sh" --targets | paste -sd' ' | sed 's/ /`, `/g')
    if [ -z "$fw_targets" ]; then
        say "\`$base\` has no higher version branch to forward-port to: \`/mergebot r+\` without \`fw+\`."
        exit 0
    fi
    gh label create "$fw_label" --repo "$REPO" --color 0E8A16 \
        --description "Forward-ported by the mergebot to the higher version branches once merged" > /dev/null 2>&1 || true
    gh pr edit "$PR" --repo "$REPO" --add-label "$fw_label" > /dev/null
    fw_note=" Then forward-port to \`$fw_targets\`."
fi

# ---------------------------------------------------------------------------------------------------------
# rebase
# ---------------------------------------------------------------------------------------------------------
if [ "$action" = rebase ]; then
    if rebase_branch "$head_sha"; then
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
        if ! head_sha=$(GH_TOKEN=$MERGEBOT_TOKEN gh api graphql --input - --jq .data.createCommitOnBranch.commit.oid \
            2> "$work/error" < <(python3 -c '
import json, sys
query = "mutation($input: CreateCommitOnBranchInput!) { createCommitOnBranch(input: $input) { commit { oid } } }"
print(json.dumps({"query": query, "variables": json.load(open(sys.argv[1]))}))' "$work/input.json")); then
            say "The version bump could not be pushed to the branch: $(head -c 300 "$work/error")"
            exit 0
        fi
        bump_note=" Version bump ($level): $(printf '%s; ' "${bumped_modules[@]}" | sed 's/; $//')."
        merge_state=PENDING
    fi
fi

# a branch behind its target branch is rebased first: its CI result was for the old base, so the merge waits for CI
# on the rebased commits (the commits that are merged)
behind=$(commits_behind)
rebase_note=""
if [ "$behind" != 0 ]; then
    author=$(gh pr view "$PR" --repo "$REPO" --json author --jq .author.login)
    if [ -z "${MERGEBOT_TOKEN:-}" ]; then
        say "The branch is $behind commit(s) behind \`$base\` and the mergebot has no \`MERGEBOT_TOKEN\` secret to rebase it: @$author, please rebase it and force-push, then a maintainer merges with \`/mergebot r+\`.$bump_note"
        exit 0
    fi
    if ! rebase_branch "$head_sha"; then
        say "The branch is $behind commit(s) behind \`$base\` and cannot be rebased automatically (conflicts?): @$author, please rebase it and force-push, then a maintainer merges with \`/mergebot r+\`.$bump_note"
        exit 0
    fi
    # wait for the rebased head, so that the merge below waits for its CI and not for the CI of the old head
    old_head=$head_sha
    for _ in $(seq 1 30); do
        head_sha=$(gh pr view "$PR" --repo "$REPO" --json headRefOid --jq .headRefOid)
        [ "$head_sha" != "$old_head" ] && break
        sleep 2
    done
    if [ "$head_sha" = "$old_head" ]; then
        say "The branch was rebased on \`$base\` but GitHub does not show the rebased commits yet: \`/mergebot r+\` again in a minute.$bump_note"
        exit 0
    fi
    rebase_note=" Rebased on \`$base\` ($behind new commit(s) there): CI runs again on the rebased commits."
    merge_state=PENDING
fi

# a merge commit, as "Merge PR #12 into 20.0": the commits of the author land as they are (author, committer,
# ids), only the merge commit is of the mergebot
merge_subject="Merge PR #$PR into $base"
merge_body="Signed-off-by $ACTOR"
case "$merge_state" in
    CLEAN|HAS_HOOKS)
        gh pr merge "$PR" --repo "$REPO" --merge --subject "$merge_subject" --body "$merge_body" > /dev/null
        say "Merging now.$bump_note$fw_note" ;;
    *)
        gh pr merge "$PR" --repo "$REPO" --merge --subject "$merge_subject" --body "$merge_body" --auto > /dev/null
        say "Will merge as soon as CI is green.$bump_note$rebase_note$fw_note" ;;
esac

# follow the merge (CI may take a while), to thank the author once it is done
for _ in $(seq 1 140); do
    read -r state waiting head_sha < <(gh pr view "$PR" --repo "$REPO" --json state,autoMergeRequest,headRefOid \
        --jq '"\(.state) \(.autoMergeRequest != null) \(.headRefOid)"')
    [ "$state" = MERGED ] && break
    [ "$state" = CLOSED ] && exit 0
    # the merge was cancelled, or CI failed
    [ "$waiting" = false ] && exit 0
    # another pull request was merged meanwhile: rebase again, so that CI runs on the commits that are merged (a
    # push of a maintainer keeps the merge waiting)
    behind=$(commits_behind)
    if [ "$behind" != 0 ] && [ "$behind" != '?' ] && [ -n "${MERGEBOT_TOKEN:-}" ]; then
        if rebase_branch "$head_sha"; then
            say "\`$base\` moved ($behind new commit(s)): rebased again, CI runs again on the rebased commits."
        else
            gh pr merge "$PR" --repo "$REPO" --disable-auto > /dev/null 2>&1 || true
            say "\`$base\` moved and the branch cannot be rebased automatically (conflicts?): merge cancelled. @$(gh pr view "$PR" --repo "$REPO" --json author --jq .author.login), please rebase it and force-push, then a maintainer merges with \`/mergebot r+\`."
            exit 0
        fi
    fi
    sleep 60
done
[ "$state" = MERGED ] || exit 0
bash "$scripts/mergebot_thanks.sh"
if [ "$forward" = true ]; then
    bash "$scripts/mergebot_forward_port.sh"
fi
