#!/usr/bin/env bash

set -euo pipefail

interval_seconds="${1:-5}"

has_non_md_changes() {
  local line path

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    path="${line:3}"

    if [[ "$path" == *" -> "* ]]; then
      path="${path##* -> }"
    fi

    if [[ "$path" != *.md ]]; then
      return 0
    fi
  done < <(git status --porcelain)

  return 1
}

while true; do
  if ! has_non_md_changes; then
    printf 'Worktree ready: clean or only Markdown changes remain.\n'
    exit 0
  fi

  printf 'Waiting for non-Markdown changes to clear...\n'
  sleep "$interval_seconds"
done
