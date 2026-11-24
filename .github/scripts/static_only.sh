#!/usr/bin/env bash
# skip=true when every file a pull request (or a push) changes is a store page file or an image: the tests and the
# lint have nothing to check then, so their jobs end at once, green. Anything else, or any doubt: skip=false.
set -uo pipefail

files=""
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ -n "${PR:-}" ]; then
    files=$(gh api "repos/$GITHUB_REPOSITORY/pulls/$PR/files" --paginate --jq '.[].filename') || files=""
elif [ "${GITHUB_EVENT_NAME:-}" = "push" ] && [ -n "${BEFORE:-}" ] && [ "${BEFORE//0/}" != "" ]; then
    # the compare lists 300 files at most: with that many, run everything
    files=$(gh api "repos/$GITHUB_REPOSITORY/compare/$BEFORE...$GITHUB_SHA" --jq 'if (.files | length) >= 300 then "-" else .files[].filename end') || files=""
fi

skip=false
if [ -n "$files" ] && ! grep -vqE '(^|/)static/description/|\.(png|jpe?g|gif|svg|webp|ico)$' <<<"$files"; then
    skip=true
fi
printf '%s\n' "$files" | sed 's/^/  /'
echo "skip=$skip"
echo "skip=$skip" >> "$GITHUB_OUTPUT"
