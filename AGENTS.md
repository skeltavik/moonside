# Repository Instructions

- Use `uv` for Python dependency and test workflows.
- Do not install into the system Python environment.
- Use the repo-local virtual environment at `.venv` when needed.
- Python 3.14 is the supported development and CI runtime.
- Install and lock development dependencies with `uv sync --locked --all-groups`.
- Run lint with `uv run --locked ruff check custom_components/moonside scripts tests`.
- Check formatting before pushing with `uv run --locked ruff format --check custom_components/moonside scripts tests`.
- Run tests with `PYTHONPATH=. uv run --locked pytest`.
- `PYTHONPATH=.` is required because this repository is not installed as a Python package.

## Keeping This File Current

- Update this file when integration invariants, supported runtimes, verification
  procedures, or release/security policy change. Keep user-facing changes in
  `README.md` and `CHANGELOG.md` too.
- Record verified facts and important failure modes, not conversation transcripts
  or temporary progress. Date verification snapshots; they are not permanent
  guarantees or required test counts.
- Never record credentials, tokens, real account data, or private HA configuration.

## Integration Invariants

1. **Credential-safe cloud failures** (`custom_components/moonside/cloud.py`):
   never include request URLs, credentials, untrusted exception text, or arbitrary
   provider response bodies in errors or logs. Formatted exception chains must
   also be safe. Preserve only recognized Firebase authentication categories.
   Regression coverage: `tests/test_cloud_security.py`.
2. **Observable command failures** (`light.py`, `__init__.py`): a rejected BLE
   operation must raise a Home Assistant error, not return normal success.
   Custom actions targeting several lights must attempt all selected Moonside
   lights before reporting failures. Do not invent successful lamp state.
3. **Effect and brightness together** (`light.py`, `moonside.py`): apply an effect
   and explicitly requested brightness in one BLE command batch. Wake an off lamp
   as needed; effect-only requests must not send an unnecessary brightness
   command. Publish the combined state only after the batch succeeds.
4. **Cloud cannot block or undo local control** (`moonside.py`): HTTP requests
   must not hold the BLE command lock. Serialize cloud refreshes separately and
   reconcile under the BLE lock only if no intervening local write occurred.
   Successful-write generation/grace bookkeeping belongs centrally in
   `_send_commands`, including all pixel paths. Partial writes invalidate cached
   power and stale cloud snapshots. Cover zero-second grace windows as well.
5. **Recover real device metadata** (`moonside.py`, `__init__.py`): learn BLE model
   names from advertisements/discovered devices, never a user-chosen display name.
   Persist recovered `ble_name`, update the HA device registry model, preserve
   custom names, and do not reload for metadata-only changes. Use
   `async_get_device_by_identifier((DOMAIN, address), entry.entry_id)`; the
   unscoped `async_get_device` lookup is deprecated. Unknown devices stay generic;
   do not bypass Lighthouse-only pixel checks by guessing.
6. **Tested compatibility floor**: Home Assistant 2026.10.0 is the supported
   minimum, matching the tested locked environment. Keep `hacs.json`, development
   requirements, lockfile, README, and CI consistent. Python requires
   `>=3.14.2,<3.15`; older HA support must be demonstrated, not assumed.
7. **Versioned distribution**: HACS uses `zip_release: true` and downloads
   `moonside.zip` release assets, not moving default-branch snapshots. Keep
   `pyproject.toml`, the integration manifest, and the `v<version>` tag consistent.
   Document release changes in `CHANGELOG.md`.

Behavioral regressions for items 2–5 are in `tests/test_latency.py`. Exercise the
real command/state pipeline and HA service registry; replace only hardware or
network boundaries. Avoid tests that merely assert forwarding, wording, or source
text. Release artifact/verification behavior is covered by `tests/test_release.py`.

## Verification

- Run the full test, lint, and formatting commands above before publishing.
- Run `uv run --locked bandit -c pyproject.toml -r custom_components/moonside scripts`.
- Run the dependency audit from `.github/workflows/validate.yml`, retaining only
  its explicitly documented advisory exceptions; do not bypass new findings.
- Validate workflow changes with
  `go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 .github/workflows/validate.yml .github/workflows/release.yml`.
- For significant behavior or packaging changes, also load the built ZIP in an
  isolated HA instance and exercise light/sensor creation, services, state,
  failure handling, metadata persistence, and unload. Automated tests alone do
  not establish physical lamp or firmware compatibility.
- Do not use a live HA installation, real cloud account, or physical lights as
  routine test fixtures without authorization.

## Immutable Releases

- Keep GitHub's repository immutable-releases policy enabled. This is a
  repository setting, not a property supplied by a tag name or checksum.
  Administrators can inspect it with
  `gh api repos/skeltavik/moonside/immutable-releases`.
- The ordinary workflow token cannot change that policy. Do not add an
  administrator PAT merely to inspect it from the release workflow.
- Build with
  `uv run --locked python scripts/build_release.py v<version> /tmp/moonside.zip`.
  The builder checks tag/project/manifest versions before writing. The archive
  must contain integration files and branding at its root, without wrapper
  directories or Python caches.
- `.github/workflows/release.yml` runs the reusable validation workflow before
  publication, builds `moonside.zip` and `SHA256SUMS`, uploads both to a **draft**,
  then publishes. Never publish before uploading the assets.
- Require the published release to report `immutable: true` and verify its
  signed GitHub release attestation. Attestations are generated asynchronously:
  publication can succeed before `gh release verify` can see them. The workflow
  retries at most 12 times with 10-second gaps, within a five-minute release job
  deadline, and fails closed if verification never succeeds.
- Use `gh release verify v<version>` and
  `gh release verify-asset v<version> /path/to/moonside.zip` to verify provenance.
  Also check the downloaded archive against `SHA256SUMS`.
- Never replace published assets, move/delete their tag, or recreate an immutable
  release to hide a failed verification step. Inspect actual publication state
  before retrying a partially completed release. Ship product corrections under
  a new version; automation-only fixes can go to `main` without altering the
  already published artifact.
- Immutable releases prevent tag/asset replacement; they do not make malicious
  code or compromised dependencies safe. Keep workflow actions pinned and review
  dependencies. Do not claim complete supply-chain protection.
- Obtain explicit authorization for commits, pushes, tags, and publication; a
  request to edit repository files is not standing permission to release them.

## Verified Snapshot — 2026-11-07

- All seven invariants above were implemented and reviewed.
- Published immutable release:
  [v1.1.0](https://github.com/skeltavik/moonside/releases/tag/v1.1.0), integration
  commit `58b0ef4`. Its ZIP checksum and signed release/asset attestations were
  verified, and the downloaded ZIP matched the integration source byte-for-byte.
- An isolated HA smoke run loaded the published ZIP and exercised one light,
  three diagnostic sensors, effect plus brightness, pixel control, model
  persistence/device-registry update, failed BLE writes, and unload.
- The first release job published successfully but failed its immediate
  attestation check. Commit `48be948` added bounded waiting and regressions on
  `main`; the immutable v1.1.0 tag and assets were left untouched.
- At `48be948`, 181 tests passed; lint, formatting, Bandit, dependency audit, and
  workflow validation passed. GitHub tests, HACS, and Hassfest were
  [green on main](https://github.com/skeltavik/moonside/actions/runs/42398790829).
- No physical lamp test was performed and the user's live HA installation was
  not upgraded. BLE/network boundaries in the smoke run were controlled.
