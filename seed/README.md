# One-time cloud state bootstrap

`jobs.sqlite.gz` is a short-lived deployment snapshot used only when the first GitHub Actions run has no cache yet. It preserves stable job identities, delivered-job markers, and the latest complete per-company cursors so moving from the local schedule does not duplicate alerts.

The snapshot is intentionally stripped: HTTP response bodies, rejected-job sightings, and raw job-description payloads are removed. The workflow validates SQLite integrity and ignores the snapshot if its newest usable run is more than 72 hours old. Once the first hosted state cache is verified, the compressed database is removed from the working tree; a later total cache loss falls back to a fresh seven-day initialization.
