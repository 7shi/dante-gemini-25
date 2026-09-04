# Site templates

Jinja2 templates and static assets used by [build.py](build.py) to
generate the static site published at
[7shi.github.io/dante-gemini-25](https://7shi.github.io/dante-gemini-25/).

file|description
----|----
[canto.html](canto.html) | per-canto page: a line-by-line Italian/English/Japanese trilingual layout
[summary.html](summary.html) | per-canticle summary page: title illustration + English/Japanese segment summaries for every canto
[index.html](index.html) | landing page
[_sidebar.html](_sidebar.html) | shared sidebar/navigation include
[static/](static/) | CSS copied as-is into `dist/`

**`build.py` reads only the expanded `it/`, `en/`, `ja/` files** (`{part}/NN.txt`,
`{part}.md`, `{part}-1.md`) — it never touches `en.jsonl` / `ja.jsonl`.
Translation fixes are made directly in the expanded files under `en/` and
`ja/`; if `make convert` or `make summarize1` (run from `it/`) is re-run
afterward, it regenerates those files from the jsonl and overwrites any such
hand-fix.

`it/{part}/NN.txt` (the Italian source, split per canto) is not tracked in
git — if missing, run `make -C it all split` first (see
[it/README.md](../it/README.md)).

## Build and Deploy

The [online reader](https://7shi.github.io/dante-gemini-25/) is a static
site generated from these templates and published to GitHub Pages.

### Local build

```bash
# Compress images/ illustrations into dist/images/, then build the HTML pages
make build

# Serve dist/ locally for a preview (localhost:8000)
make serve

# Remove build artifacts
make clean-dist
```

`make build` depends on `make images` (via `images/compress.py`), which in
turn requires the illustrations described in
[../images/README.md](../images/README.md) to already be in place under
`images/`.

### Deploying to GitHub Pages

```bash
# Build, then push dist/ to the gh-pages branch
make deploy
```

`deploy.sh` checks out the `gh-pages` branch into `.gh-pages-worktree/` via
`git worktree`, replaces its contents with `dist/`, and commits and pushes.
It is a no-op when there is nothing to deploy.

### First-time setup

The `gh-pages` branch is created automatically on the first `make deploy`.

In the GitHub UI:

1. Open **Settings → Pages** on the repository
2. Set **Source** to `Deploy from a branch`
3. Set **Branch** to `gh-pages` / `/ (root)` and **Save**
