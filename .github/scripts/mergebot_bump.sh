#!/usr/bin/env bash
# Bump the version of the modules changed by a merged pull request, once, in one "[BOT] post-merge updates" commit
# on its target branch. Left as they are: a pull request with the label nobump or not on a version branch
# (N.0), and the modules it adds or whose version it changes itself. The commit is made with MERGEBOT_TOKEN, a token
# of an admin of the repository, the required checks of the branch do not apply to it. If the branch moves meanwhile,
# the versions are read again. Nothing of the pull request is executed.
#
#   mergebot_bump.sh [major|minor|patch]    patch by default
#
# Environment: GH_TOKEN, MERGEBOT_TOKEN, REPO, PR.
set -euo pipefail

level=${1:-patch}
scripts=$(dirname "$0")
marker='<!-- mergebot-bump -->'

say() { gh pr comment "$PR" --repo "$REPO" --body "$1" > /dev/null; }

if gh api "repos/$REPO/issues/$PR/comments" --paginate --jq '.[].body' | grep -qF "$marker"; then
    exit 0
fi
read -r base nobump < <(gh pr view "$PR" --repo "$REPO" --json baseRefName,labels \
    --jq '"\(.baseRefName) \(any(.labels[]; .name == "nobump"))"')
[ "$nobump" = false ] && [[ $base =~ ^[0-9]+\.0$ ]] || exit 0
if [ -z "${MERGEBOT_TOKEN:-}" ]; then
    say "The version of the modules was not raised: the mergebot has no \`MERGEBOT_TOKEN\` secret."
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
gh api "repos/$REPO/pulls/$PR/files" --paginate --jq '.[]' > "$work/files"
: > "$work/error"
# the modules of the pull request, without the new or renamed ones and those whose version it changes
modules=$(python3 - "$work/files" <<'PY'
import json, re, sys
changed, kept = set(), set()
for line in open(sys.argv[1], encoding='utf-8'):
    file = json.loads(line)
    module, _, rest = file['filename'].partition('/')
    if not rest or not re.fullmatch(r'\w+', module):
        continue
    changed.add(module)
    if rest == '__manifest__.py' and (
        file['status'] != 'modified'
        or re.search(r"""^[-+]\s*['"]version['"]\s*:""", file.get('patch', ''), re.M)
    ):
        kept.add(module)
print('\n'.join(sorted(changed - kept)))
PY
)
[ -n "$modules" ] || exit 0

# one try: the commit on the current head of the branch; prints what it did
bump() {
    local head additions module path notes=()
    head=$(gh api "repos/$REPO/branches/$base" --jq .commit.sha) || return 1
    additions="$work/additions.jsonl"
    : > "$additions"
    for module in $modules; do
        path="$module/__manifest__.py"
        # a module removed meanwhile, or not on this branch
        gh api "repos/$REPO/contents/$path?ref=$head" --jq .content 2>/dev/null | base64 -d > "$work/manifest" || continue
        [ -s "$work/manifest" ] || continue
        python3 "$scripts/mergebot_version.py" "$level" < "$work/manifest" > "$work/new" 2> "$work/log" || continue
        python3 -c 'import base64, json, sys; print(json.dumps({"path": sys.argv[1], "contents": base64.b64encode(open(sys.argv[2], "rb").read()).decode()}))' \
            "$path" "$work/new" >> "$additions"
        notes+=("\`$module\` $(cat "$work/log")")
    done
    [ -s "$additions" ] || return 0
    python3 - "$additions" "$REPO" "$base" "$head" "[BOT] post-merge updates" > "$work/input.json" <<'PY'
import json, sys
print(json.dumps({
    'query': 'mutation($input: CreateCommitOnBranchInput!) { createCommitOnBranch(input: $input) { commit { oid } } }',
    'variables': {'input': {
        'branch': {'repositoryNameWithOwner': sys.argv[2], 'branchName': sys.argv[3]},
        'expectedHeadOid': sys.argv[4],
        'message': {'headline': sys.argv[5]},
        'fileChanges': {'additions': [json.loads(line) for line in open(sys.argv[1], encoding='utf-8')]},
    }},
}))
PY
    GH_TOKEN=$MERGEBOT_TOKEN gh api graphql --input "$work/input.json" > /dev/null 2> "$work/error" || return 1
    printf '%s, ' "${notes[@]}" | sed 's/, $//'
}

for attempt in 1 2 3 4 5; do
    if done_note=$(bump); then
        if [ -n "$done_note" ]; then
            say "Version bump ($level) on \`$base\`: $done_note.
$marker"
        fi
        exit 0
    fi
    [ "$attempt" = 5 ] || sleep $((attempt * 5))
done
say "The version bump ($level) could not be committed on \`$base\`, raise the version of the modules by hand: $(head -c 300 "$work/error")"
