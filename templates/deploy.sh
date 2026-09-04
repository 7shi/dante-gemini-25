#!/usr/bin/env bash
# Deploy dante-gemini-25 to GitHub Pages (gh-pages branch).
# Run via `bash templates/deploy.sh`; chmod +x is not required.
# Prerequisite: `make build` has been run and dist/ contains the static site.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
WORKTREE_DIR="$REPO_ROOT/.gh-pages-worktree"
BRANCH="gh-pages"

if [ ! -d "$DIST_DIR" ]; then
    echo "Error: $DIST_DIR not found. Run 'make build' first." >&2
    exit 1
fi

cd "$REPO_ROOT"
COMMIT_SHA="$(git rev-parse --short HEAD)"

# Clean up an existing worktree (leftover from a previous failed run)
if [ -d "$WORKTREE_DIR" ]; then
    git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
fi

# Set up the gh-pages branch as a worktree (creating it if it doesn't exist yet)
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git worktree add "$WORKTREE_DIR" "$BRANCH"
elif git ls-remote --heads origin "$BRANCH" | grep -q "$BRANCH"; then
    git worktree add -B "$BRANCH" "$WORKTREE_DIR" "origin/$BRANCH"
else
    git worktree add --orphan -b "$BRANCH" "$WORKTREE_DIR"
fi

# Remove existing files in the worktree (.git is managed by the worktree, unaffected)
find "$WORKTREE_DIR" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +

# Copy the contents of dist into the worktree
cp -r "$DIST_DIR"/. "$WORKTREE_DIR"/

# Disable Jekyll processing
touch "$WORKTREE_DIR/.nojekyll"

# Commit & push
cd "$WORKTREE_DIR"
git add -A
if git diff --cached --quiet; then
    echo "No changes to deploy."
else
    git commit -m "Deploy from $COMMIT_SHA"
    git push origin "$BRANCH"
fi

# Clean up
cd "$REPO_ROOT"
git worktree remove --force "$WORKTREE_DIR"

echo "Deployed to $BRANCH branch."
