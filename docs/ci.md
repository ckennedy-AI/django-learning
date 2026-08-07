# CI

`.github/workflows/ci.yml`, added in Phase 14. Four jobs, three of them parallel, plus the
parts of CI that are not in the repository at all.

`ci.yml` itself is heavily commented, and those comments explain why each line is what it
is. This file covers what a comment in that file cannot: the configuration that lives in
GitHub's repository settings rather than in any file, how to reproduce a CI failure
locally, and the failure modes worth recognising on sight.

## The pipeline

```
                push to main/dev, or pull_request targeting them
                                  |
                 +----------------+----------------+
                 |                |                |
               lint             test             build
             ~30 sec          ~3 min          ~5 min cold
             ruff check       services:       docker buildx
             ruff format      postgres        cache to gha
                              redis
                 |                |                |
                 +----------------+----------------+
                                  |
                               deploy
                     only on push to dev, never on a PR
                     environment: staging, waits for approval
                               (a stub)
```

Each job answers a question the others cannot:

| Job | Proves | Needs |
|---|---|---|
| `lint` | the source is formatted and lint-clean | nothing but ruff |
| `test` | the code is correct against real Postgres with pgvector, and the migration graph is complete | service containers |
| `build` | the **image** still builds, which `test` never checks because it installs `requirements.txt` straight onto the runner and never reads the Dockerfile | buildx |
| `deploy` | the shape of a gated release: fan-in, branch condition, human approval | nothing, it deploys nothing |

`build` is deliberately not chained behind `test`. They answer independent questions, and
`build` is the slowest job because the Dockerfile installs PyTorch, so putting it in front
of the test feedback loop would cost minutes for no information.

## What is not in the repository

Three things are required for CI to behave as documented, and none of them is a file. A
fresh clone or a fork gets none of them, which is the standard way this configuration goes
missing without any commit recording it.

**Branch protection on `dev`.** Settings → Branches → branch protection rules. Require
status checks to pass before merging, and select **`lint`, `test`, and `build`** only.

**Do not add `deploy` as a required check.** It fires only on `push` to `dev`, so it never
reports on a pull request, and a required check that cannot arrive blocks every merge
forever waiting for it. This is the single most likely way to wedge the repository, and
the symptom, a check stuck on "Expected" and waiting for a status to be reported that never
arrives, does not name the cause.

**The `staging` environment.** Settings → Environments → `staging`, with a required
reviewer. That reviewer requirement is the only thing that makes `deploy` pause; the
`environment:` key in `ci.yml` references the environment but cannot create it or set its
rules. With no environment configured, GitHub creates one implicitly on first use and the
job runs straight through, which looks identical in the workflow file and completely
different in the run.

**Nothing needs a repository secret.** The `test` job's credentials are plain literals in
`ci.yml` on purpose: they are throwaway values for a database created and destroyed inside
one job. Putting them in Secrets would imply they protect something and would hide the
connection strings from whoever is debugging a connection failure.

## The one structural difference from Docker Compose

Job steps run **on the runner host**, not inside a container. Service containers are
started alongside the job and reached over published ports on `localhost`.

```yaml
DATABASE_URL: postgres://postgres:postgres@localhost:5432/onboarding
```

Compare `.env`, where the same variable says `@db:5432`. Compose service names resolve on
the Compose network; on a runner there is no such network unless the job declares its own
`container:` and joins one. That is why the `ports:` mapping under each service is not
optional here, and why copying `DATABASE_URL` from `.env` into a workflow produces a
connection failure that reads like a database problem.

Everything else is the same on purpose. The Postgres image is `pgvector/pgvector:pg17` in
both places, for the same reason: the stock `postgres` image ships no vector extension
binary, so `0002_enable_pgvector` cannot succeed on it and every migration behind it fails.
Both health checks use `-h 127.0.0.1` for the same reason too, since on a fresh data
directory the image runs `initdb` against a temporary server bound to the unix socket only,
and a socket-based `pg_isready` would report healthy during that window.

**Redis is present and unused.** `manage.py test` sets `TESTING` in `config/settings.py`,
which swaps `CACHES` to `LocMemCache` and turns on `CELERY_TASK_ALWAYS_EAGER`, so the suite
opens no connection to it. `REDIS_URL` is still required, because `CACHES` is built from it
at import time before the `TESTING` block replaces the entry. A green run is not evidence
that Redis works.

## Reproducing a CI failure locally

CI runs the same commands the container does, so most failures reproduce directly. The
exception is dependency resolution, which is the one place the two environments genuinely
differ.

```powershell
# lint, both steps, in the order CI runs them
docker compose exec web ruff check .
docker compose exec web ruff format --check .

# test, all three steps
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test

# build
docker compose build --no-cache web
```

`ruff format --check` rather than `ruff format` is the difference that matters: the plain
form rewrites files and exits zero, so running it locally will make a failing check pass
without showing you what changed. Run `--check` first, read the file list, then format.

The `makemigrations --check --dry-run` step is the cheapest guard in the pipeline and it
catches gotcha 14: a model present in `onboarding/models/` but missing from
`models/__init__.py` is invisible to the app registry, and `makemigrations` reports it as a
`DeleteModel` rather than as a missing import. Catching it here means it surfaces as "you
have unmade migrations" on a pull request instead of as a dropped table for whoever
migrates next.

## Things that bite

**Ruff versions drifting.** `lint` installs ruff by reading the pin out of
`requirements.txt` rather than hardcoding a version, because a hardcoded version in two
files eventually disagrees, and the symptom is a lint failure that does not reproduce in
the container. If a lint failure will not reproduce locally, check the installed versions
before checking the code.

**The two pip index flags are load-bearing, in CI as well as in the Dockerfile.** On Linux
the default PyPI `torch` wheel hard-depends on the `nvidia-cu13` CUDA runtime packages,
which are gigabytes of download for a project that runs embeddings on CPU. Dropping
`--index-url https://download.pytorch.org/whl/cpu` from either place does not fail, it just
gets slow and large, which is the kind of regression nobody notices until the runner times
out.

**`--no-cache-dir` is in the Dockerfile and deliberately absent from the CI install.** In
the image it keeps a layer small. On the runner it would empty the directory
`actions/setup-python` just restored, making the pip cache pointless.

**Only the `test` job caches pip, on purpose.** `setup-python` keys its cache on the
dependency file hash plus OS and Python version, so both jobs would share one key while
wanting different contents: one installs a lone ruff wheel, the other installs PyTorch. A
key is never overwritten once written, so the cheap cache could permanently shadow the
expensive one.

**`concurrency` cancels superseded runs.** Two pushes in quick succession to the same ref
leave only the newer run. A run that reports "cancelled" rather than failed usually means
exactly that, not an infrastructure problem. The group is keyed on ref as well as workflow
so a push to `dev` never cancels a pull request's checks.

**`push` is limited to `main` and `dev`.** A phase branch is covered by the
`pull_request` trigger, which is the run that gates the merge. Without that narrowing, a
branch with an open pull request would run the whole pipeline twice per commit.

**A red X on an old commit after a force push.** Check-run results attach to a commit SHA,
not to a branch, so rewriting history leaves the old SHA's result behind. Look at the run's
commit, not the branch name.

**The buildx cache is not governed by the workflow's `permissions` block.** `type=gha`
authenticates with `ACTIONS_RUNTIME_TOKEN`, a separate credential from `GITHUB_TOKEN`.
Tightening `permissions: contents: read` does not break the layer cache, which is worth
knowing before someone loosens it trying to fix a slow build.

**The image is built and never published.** `push: false` and `load: false`, since there is
no registry in this pipeline and nothing runs the image. The tag the stub deploy prints
names an artifact that exists only inside that run.

## Known gaps

- **Nothing is deployed.** `deploy` echoes what it would deploy. A real one would push the
  image to a registry and roll it out, and `build` would have to publish rather than
  discard it.
- **Coverage is not measured or enforced.** The suite either passes or it does not.
- **`main` has the same workflow but no gate.** Branch protection is configured on `dev`
  only, which matches how this repository is actually used: phase branches merge to `dev`,
  and `dev` merges to `main` at the end.
- **No security or dependency scanning.** No Dependabot, no `pip-audit`, no image scan.
  Reasonable for a learning project that is not deploying, and the first thing to add if it
  ever were.
