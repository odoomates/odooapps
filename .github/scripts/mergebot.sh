#!/usr/bin/env bash
# The mergebot: runs the command of a pull request comment (its first line, starting with /mergebot). A wrong command
# of a maintainer is declined with a comment, and nothing is done.
#   /mergebot r+                 merge the pull request (a merge commit "Merge PR #N into <branch>", the commits of
#                               the author unchanged) once CI is green, then bump the patch version of the modules
#                               changed (mergebot_bump.sh), thank the author and delete its branch, if of this
#                               repository;
#                               a branch behind its target branch is rebased first, and CI runs again on the rebased
#                               commits before the merge
#   /mergebot r+ minor|major|patch
#                               the same, with this level of version bump
#   /mergebot r+ nobump          the same, without a version bump (the label nobump: also for a merge by hand)
#   /mergebot r+ fw+             merge, then forward-port: one pull request of its commits to every higher version
#                               branch (fw+ goes with r+, in any order, also with a bump level)
#   /mergebot r+ fw+ 19.0        the same, up to this branch included (also: fw+ upto 19.0)
#   /mergebot rebase             rebase the branch of the pull request on its target branch
#   /mergebot r-                 cancel a merge waiting for CI (and its forward-port), or waiting for a linked pull
#                               request
#   /mergebot release            sent by the bot to a linked pull request that waits: run its last /mergebot r+ again
# Linked pull requests: a line "Linked: owner/repo#12" in the description of one of them, in a repository of the same
# owner. r+ on one then waits for r+ on the other, and the second r+ merges both, each with its own command. A repository
# of MERGEBOT_LINKED_REPOS is searched for a pull request naming this one, so one side declaring it is enough.
# The rebases push to the branch of the pull request (often in a fork) with MERGEBOT_TOKEN, a token of a maintainer,
# which also starts CI again on the new commits; the bump commits on the target branch with this token, of an admin.
# Environment: GH_TOKEN, MERGEBOT_TOKEN, REPO, PR, ACTOR, COMMENT_ID, BODY, MERGEBOT_ROLES, MERGEBOT_LINKED_REPOS.
set -euo pipefail

scripts=$(dirname "$0")
read -r -a words <<< "$(printf '%s\n' "$BODY" | tr -d '\r' | grep -v '^[[:space:]]*$' | head -n 1 | tr '[:upper:]' '[:lower:]')"
[[ ${words[0]:-} == /mergebot* ]] || exit 0
action=""
level=""
forward=false
upto=""
upto_word=false
error=""
[ "${words[0]}" = /mergebot ] || error="unknown command \`${words[0]}\`"
for word in "${words[@]:1}"; do
    case "$word" in
        r+|r-|rebase|release)
            [ -z "$action" ] || error="\`$word\` with another of \`r+\`, \`r-\`, \`rebase\`"
            case "$word" in r+) action=merge ;; r-) action=cancel ;; release) action=release ;; *) action=rebase ;; esac ;;
        major|minor|patch|nobump)
            [ -z "$level" ] || error="two version bumps: \`$level\` and \`$word\`"
            level=$word ;;
        fw+) forward=true ;;
        upto) upto_word=true ;;
        *)
            if [[ $word =~ ^[0-9]+\.0$ ]]; then
                [ -z "$upto" ] || error="two last branches: \`$upto\` and \`$word\`"
                upto=$word
            else
                error="unknown word \`$word\`"
            fi ;;
    esac
done
if [ -z "$error" ]; then
    if [ -z "$action" ]; then
        error="no \`r+\`, \`r-\` or \`rebase\`"
    elif [ "$action" != merge ] && { [ -n "$level" ] || [ "$forward" = true ]; }; then
        error="\`fw+\` and the version bumps go with \`r+\`"
    elif [ -n "$upto" ] && [ "$forward" != true ]; then
        error="a last branch goes with \`fw+\`"
    elif [ "$upto_word" = true ] && [ -z "$upto" ]; then
        error="\`upto\` without a branch"
    fi
fi
fw_label=forward-port
nobump_label=nobump
linked_label=mergebot-r+

say() { gh pr comment "$PR" --repo "$REPO" --body "$1" > /dev/null; }
# the labels fw-upto-<branch>: the last branch to forward-port to
remove_upto() {
    local label
    for label in $(gh pr view "$PR" --repo "$REPO" --json labels --jq '.labels[].name | select(startswith("fw-upto-"))' 2>/dev/null || true); do
        gh api -X DELETE "repos/$REPO/issues/$PR/labels/$label" > /dev/null 2>&1 || true
    done
}
remove_nobump() { gh api -X DELETE "repos/$REPO/issues/$PR/labels/$nobump_label" > /dev/null 2>&1 || true; }
remove_linked() { gh pr edit "$PR" --repo "$REPO" --remove-label "$linked_label" > /dev/null 2>&1 || true; }

# the pull requests linked to this one, as owner/repo#12: the lines of its description, and the pull requests of the
# other repositories whose description names it
linked_prs() {
    local sibling number
    gh pr view "$PR" --repo "$REPO" --json body --jq .body | tr -d '\r' \
        | sed -nE 's/^[[:space:]]*[Ll]inked:[[:space:]]*([A-Za-z0-9._-]+\/[A-Za-z0-9._-]+#[0-9]+)[[:space:]]*$/\1/p'
    [ -n "${MERGEBOT_TOKEN:-}" ] || return 0
    for sibling in ${MERGEBOT_LINKED_REPOS:-}; do
        [ "${sibling,,}" = "${REPO,,}" ] && continue
        for number in $(GH_TOKEN=$MERGEBOT_TOKEN gh api -X GET search/issues \
            -f q="repo:$sibling is:pr is:open in:body \"Linked: $REPO#$PR\"" --jq '.items[].number' 2>/dev/null); do
            # the search matches words: 12 may also find #123
            if GH_TOKEN=$MERGEBOT_TOKEN gh pr view "$number" --repo "$sibling" --json body --jq .body | tr -d '\r' \
                | grep -qiE "^[[:space:]]*linked:[[:space:]]*$REPO#$PR[[:space:]]*$"; then
                echo "$sibling#$number"
            fi
        done
    done
}

# r+ with linked pull requests: go on only once every one of them has its r+, or is merged. Stops the command otherwise.
wait_for_linked() {
    local links link repo number info linked_state approved
    local waiting=() open=()
    links=$(linked_prs | sort -fu)
    [ -n "$links" ] || return 0
    if [ -z "${MERGEBOT_TOKEN:-}" ]; then
        say "This pull request is linked, and the mergebot has no \`MERGEBOT_TOKEN\` secret to read the other one: nothing done."
        exit 0
    fi
    gh label create "$linked_label" --repo "$REPO" --color 5319E7 \
        --description "Has its r+, and waits for r+ on a linked pull request" > /dev/null 2>&1 || true
    gh pr edit "$PR" --repo "$REPO" --add-label "$linked_label" > /dev/null
    for link in $links; do
        repo=${link%#*}
        number=${link##*#}
        if [ "${repo%%/*}" != "${REPO%%/*}" ]; then
            say "\`$link\` is not a repository of \`${REPO%%/*}\`: nothing done."
            exit 0
        fi
        if ! info=$(GH_TOKEN=$MERGEBOT_TOKEN gh pr view "$number" --repo "$repo" --json state,labels \
            --jq "\"\(.state) \([.labels[].name] | index(\"$linked_label\") != null)\"" 2>/dev/null); then
            say "The mergebot cannot read the linked pull request \`$link\`: nothing done."
            exit 0
        fi
        read -r linked_state approved <<< "$info"
        case "$linked_state" in
            MERGED) ;;
            OPEN)
                open+=("$link")
                [ "$approved" = true ] || waiting+=("$link") ;;
            *)
                say "The linked pull request \`$link\` is closed: remove the link, or reopen it. Nothing done."
                exit 0 ;;
        esac
    done
    if [ ${#waiting[@]} -gt 0 ]; then
        say "Waiting for \`/mergebot r+\` on the linked pull request: ${waiting[*]}. Both are merged then. \`/mergebot r-\` cancels."
        exit 0
    fi
    # the second r+: wakes the others up, once. A release does not, they are awake already.
    if [ -z "${MERGEBOT_RELEASED:-}" ]; then
        for link in "${open[@]}"; do
            GH_TOKEN=$MERGEBOT_TOKEN gh pr comment "${link##*#}" --repo "${link%#*}" --body "/mergebot release" > /dev/null
        done
    fi
}

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
# a wrong command does nothing but say so
if [ -n "$error" ]; then
    gh api -X POST "repos/$REPO/issues/comments/$COMMENT_ID/reactions" -f content=-1 > /dev/null
    say "Declined, nothing done: $error. The commands:
- \`/mergebot r+\`: merge, then patch version bump (\`/mergebot r+ minor\`, \`major\`, \`nobump\`)
- \`/mergebot r+ fw+\`: merge, then forward-port (\`/mergebot r+ fw+ 19.0\`: up to this branch)
- \`/mergebot rebase\`: rebase on the target branch
- \`/mergebot r-\`: cancel a merge waiting for CI or for a linked pull request"
    exit 0
fi
gh api -X POST "repos/$REPO/issues/comments/$COMMENT_ID/reactions" -f content=+1 > /dev/null

if [ "$action" = cancel ]; then
    gh pr merge "$PR" --repo "$REPO" --disable-auto > /dev/null 2>&1 || true
    gh pr edit "$PR" --repo "$REPO" --remove-label "$fw_label" > /dev/null 2>&1 || true
    remove_nobump
    remove_upto
    remove_linked
    say "Merge cancelled: the pull request will not be merged automatically."
    exit 0
fi

# a linked pull request got its r+: the last r+ of this one runs again, if it was not cancelled meanwhile
if [ "$action" = release ]; then
    if ! gh pr view "$PR" --repo "$REPO" --json labels --jq '.labels[].name' | grep -qxF "$linked_label"; then
        exit 0
    fi
    # shellcheck disable=SC2016
    command=$(gh api "repos/$REPO/issues/$PR/comments" --paginate --jq '.[]
        | select(.author_association == "OWNER" or .author_association == "MEMBER" or .author_association == "COLLABORATOR")
        | select(.body | test("^\\s*/mergebot\\s+(.*\\s)?r\\+"; "i")) | .body | split("\n")[0]' | tail -n 1)
    if [ -z "$command" ]; then
        say "The linked pull request has its r+, but the mergebot finds no \`/mergebot r+\` here: nothing done."
        exit 0
    fi
    BODY=$command MERGEBOT_RELEASED=1 exec bash "$0"
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
if [ "$action" = rebase ] && [ -z "${MERGEBOT_TOKEN:-}" ]; then
    say "The mergebot has no \`MERGEBOT_TOKEN\` secret to push to this branch: ask the author to rebase it."
    exit 0
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
    remove_upto
    fw_targets=$(bash "$scripts/mergebot_forward_port.sh" --targets | paste -sd' ' | sed 's/ /`, `/g')
    if [ -z "$fw_targets" ]; then
        say "\`$base\` has no higher version branch to forward-port to: \`/mergebot r+\` without \`fw+\`."
        exit 0
    fi
    if [ -n "$upto" ]; then
        if ! printf ' %s ' "${fw_targets//\`, \`/ }" | grep -qF " $upto "; then
            say "\`$upto\` is not a higher version branch of \`$base\`: \`$fw_targets\`."
            exit 0
        fi
        gh label create "fw-upto-$upto" --repo "$REPO" --color 0E8A16 \
            --description "The forward-port of the mergebot stops at this branch" > /dev/null 2>&1 || true
        gh api -X POST "repos/$REPO/issues/$PR/labels" -f "labels[]=fw-upto-$upto" > /dev/null
        fw_targets=$(bash "$scripts/mergebot_forward_port.sh" --targets | paste -sd' ' | sed 's/ /`, `/g')
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
wait_for_linked

# the bump comes after the merge, on the versions of the target branch by then: nobump is kept as a label, for a merge
# by hand while this waits for CI
level=${level:-patch}
if [ "$level" = nobump ]; then
    gh label create "$nobump_label" --repo "$REPO" --color C5DEF5 \
        --description "The mergebot does not bump the version of the modules once merged" > /dev/null 2>&1 || true
    gh api -X POST "repos/$REPO/issues/$PR/labels" -f "labels[]=$nobump_label" > /dev/null
    bump_note=""
else
    remove_nobump
    bump_note=" Then version bump ($level)."
fi

# a branch behind its target branch is rebased first: its CI result was for the old base, so the merge waits for CI
# on the rebased commits (the commits that are merged)
behind=$(commits_behind)
rebase_note=""
if [ "$behind" != 0 ]; then
    author=$(gh pr view "$PR" --repo "$REPO" --json author --jq .author.login)
    if [ -z "${MERGEBOT_TOKEN:-}" ]; then
        say "The branch is $behind commit(s) behind \`$base\` and the mergebot has no \`MERGEBOT_TOKEN\` secret to rebase it: @$author, please rebase it and force-push, then a maintainer merges with \`/mergebot r+\`."
        exit 0
    fi
    if ! rebase_branch "$head_sha"; then
        say "The branch is $behind commit(s) behind \`$base\` and cannot be rebased automatically (conflicts?): @$author, please rebase it and force-push, then a maintainer merges with \`/mergebot r+\`."
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
        say "The branch was rebased on \`$base\` but GitHub does not show the rebased commits yet: \`/mergebot r+\` again in a minute."
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
if [ "$state" != MERGED ]; then
    say "Still waiting for CI, and the mergebot stops following: if this merges later, it does not thank nor bump the version (\`$level\`). Better cancel with \`/mergebot r-\` and \`/mergebot r+\` again."
    exit 0
fi
if [ "$level" != nobump ]; then
    bash "$scripts/mergebot_bump.sh" "$level" || echo "::warning::The version bump failed"
fi
bash "$scripts/mergebot_thanks.sh"
# "automatically delete head branches" of GitHub does not act on the merges of the bot. Only a branch of this
# repository, not a version branch, and one no open pull request still needs (the forward-port reads refs/pull)
if [ "$head_repo" = "$REPO" ] && ! [[ $head_branch =~ ^([0-9]+\.0|master)$ ]] \
    && [ "$(gh pr list --repo "$REPO" --state open --head "$head_branch" --json number --jq length)" = 0 ] \
    && [ "$(gh pr list --repo "$REPO" --state open --base "$head_branch" --json number --jq length)" = 0 ]; then
    gh api -X DELETE "repos/$REPO/git/refs/heads/$head_branch" > /dev/null \
        || echo "::warning::The branch $head_branch could not be deleted"
fi
if [ "$forward" = true ]; then
    bash "$scripts/mergebot_forward_port.sh"
fi
