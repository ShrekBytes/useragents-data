# The `latest/` directory is retired

`latest/{windows,mac,linux,iphone,ipad,ipod,android,tablet}.json` are deleted rather
than migrated. Their contents were frozen at browser version 134 while claiming to be
current.

The directory is not merely out of date — the concept it names no longer exists.
Our sources offer a weekly rolling window and a lifetime aggregate. Neither is
"latest." Keeping the files under a deprecated alias would keep a filename
advertising a freshness guarantee the data cannot make. Retiring the name is the
only way the error is actually corrected.

Their consumers should move to the per-category files, which are regenerated from
the canonical records on every run and cannot drift out of sync with them.
