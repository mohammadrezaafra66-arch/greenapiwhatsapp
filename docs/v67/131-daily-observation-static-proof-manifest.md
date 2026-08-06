# V67.1 — Observation Static Proof Manifest

## Name

`ObservationStaticProofManifest`

## Version

`v67.owner.daily-observation.static-proof.1`

## Contents

- deployed_git_sha (env `V67_DEPLOYED_GIT_SHA` / `GIT_SHA` or `git rev-parse HEAD`)
- source_branch
- shadow_version, daily observation contract version, evidence version
- migration_revision (from alembic when available)
- test / isolation references (names only)
- manifest_status: MATCH | MISMATCH | MISSING | UNKNOWN

## Rules

- Secrets forbidden
- Does not decide daily PASS alone
- MISMATCH → validator FAIL (fail-closed)
- MISSING/UNKNOWN → cannot unlock PASS
- Immutable versioned artifact shape; rebuilt at report generation time from release metadata
