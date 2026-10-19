# Local django clone for ancestry checks

## A clone already exists

Path: /private/tmp/claude-501/-Users-nicholaswu-Downloads-TU-Delft-2026-2027/3e95dd8e-3f10-48fd-a708-6a14355885eb/scratchpad/repos/django
Made with `git clone --filter=blob:none --no-checkout https://github.com/django/django.git` on 2026-10-19. It took **5.6 s**, and `.git` is 68 MB (392k objects: all commits and trees, no blobs). It is a promisor remote with filter `blob:none`. origin/main head is 11af25c0ae (2026-10-19). There are 5 remote branches and 522 tags.
The scratchpad is temporary. For the project, re-clone into something like `<MemRev>/.cache/repos/django` (gitignored), or let the tool clone on first use.

## Why blob:none is enough

- `git cat-file -e <sha>^{commit}` (does the revision exist?) and `git merge-base --is-ancestor S T` (exit 0 = ancestor, 1 = not, 128 = bad object) only need commit objects. Both work offline in a blob:none clone and fetch nothing.
- `git show -s --format=%cI <sha>` (committer date, for ordering) only needs the commit too.
- `git diff --name-only S T [-- path]` only needs trees, so it doesn't fetch either. This is what file-change invalidation needs (spec: the "file-change invalidation" mechanism).
- Anything that reads file contents (`git show T:path`, `git diff` with content/`--stat`, `git archive`, checkout) **fetches the blobs lazily from GitHub**. It works but needs network and is slower per call. Example: `git show <sha>:django/__init__.py` took 0.55 s, and `git diff --stat` over 183 files took 0.86 s. If a step needs a lot of contents offline (e.g. `git archive T` to feed the Docker container), either accept the lazy fetch or use a full clone.
- A full clone of django is roughly 300–400 MB of .git and takes about 1–3 minutes. That is fine too, but unnecessary for ancestry checks.
- Use `--no-checkout` (or `--bare`) because the tool never needs a working tree on the host. For per-revision source use `git worktree add --detach <dir> <sha>` (a lazy fetch in a blob:none clone) or `git archive`.

## Results on the SWE-bench Verified django instances

- All 231 django base_commits exist in the clone (`cat-file -e` OK), and all are ancestors of origin/main.
- Within each version, sorted by committer date, every ordered pair (S earlier, T later) passed `--is-ancestor`: 3772 pairs, 0 failures. As expected, django's main is linear for these.
- 3772 subprocess calls took 70 s, about 18 ms each, mostly process spawn. If speed matters:
  - `git commit-graph write --reachable` (0.4 s, once) speeds up ancestry walks;
  - only check the pairs you actually build (at most 3 targets per source, so about 3x231 calls);
  - batching tricks (one `git rev-list` per source) are possible but not worth the complexity.
- Exit codes: 0 = ancestor, 1 = not an ancestor, 128 = unknown object, which maps to the "source revision not in repository" exclusion.

## Python helper sketch

```python
def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)

def commit_exists(repo, sha) -> bool:
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0

def is_ancestor(repo, s, t) -> bool:
    rc = git(repo, "merge-base", "--is-ancestor", s, t).returncode
    if rc not in (0, 1):
        raise ValueError(f"unknown revision {s} or {t}")
    return rc == 0
```
Note the f-string brace escaping: `^{commit}` needs `{{commit}}` inside an f-string.
For tests, build a tiny throwaway repo in `tmp_path` (`git init`, 3 commits, one side branch) rather than depending on the django clone. Mark real-django tests separately.

## Ensure-clone pattern

```
if not (dest / ".git").exists() and not (dest / "HEAD").exists():
    git clone --filter=blob:none --no-checkout https://github.com/django/django.git dest
# refresh when a sha is missing:
git -C dest fetch --filter=blob:none origin
```
Also set `git -C dest config core.commitGraph true`, which is on by default in modern git, and run `git commit-graph write --reachable` after cloning or fetching.
