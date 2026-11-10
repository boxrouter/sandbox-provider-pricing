# Releasing

The release workflow runs when a version tag is pushed, or by an
explicit workflow dispatch. It verifies that the tag matches the package version and immutable source
inputs before building the release assets. There is no automatic version-bump workflow.

Prepare the next unused package version in a pull request. After its main commit's Checks and Public
text boundary succeed, tag that exact commit. A tag push starts the publisher; do not dispatch another
publisher while it is queued or running. Verify the published `SHA256SUMS` before a consumer pins it.

In the pull request that will be released:

1. Add one line per user-visible change under `Unreleased` in [CHANGELOG.md](CHANGELOG.md).
2. If it adds a price file (in `src/sandbox_provider_pricing/providers/<id>/prices/`), run
   `make release-digests` and commit `tests/released-digests.txt`. The tests fail after the release if a shipped price file is not listed.
3. To pick the version yourself, such as a minor release for a change to a schema's meaning, set
   it in `pyproject.toml`, run `uv lock`, and rename `Unreleased` to that version.

After a release, check that its page lists the wheel, `price-sheet.json`, `price-sheet.schema.json`,
`conformance.json`, `cost-method.json`, `cost-method.schema.json` and `SHA256SUMS`.

## Consumer repins

A stable release repins BoxRouter's internal consumers: each records the new release in its
pins and lockfiles, replays its own pricing tests against it and pushes the validated repin commit
to `main`; there is no repin pull request. A consumer that already pins the release reports
"already applied".

To rerun one or preview it, dispatch `Repin consumers on release` with the tag. Set `dry_run` to plan,
bump, regenerate and validate each consumer without pushing. Each consumer's checks also compare
its pricing pin with the other consumers' and fail naming both versions when they differ.
