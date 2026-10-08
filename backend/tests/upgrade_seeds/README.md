# Upgrade seeds

The rows the upgrade test (`deploy/upgrade_test.py`, OPS-4) puts in the previous release's database before upgrading it. Each file is named after the migration revision whose tables or columns it fills, such as `0002.sql`, and is written against that revision's schema.

A migration that adds a table needs a seed here. The test fails if a table has no rows once the seeds are applied.
