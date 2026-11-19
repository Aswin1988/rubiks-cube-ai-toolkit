# Reproducible Research Policy

Research claims must be traceable to a versioned corpus and executable command.

Every benchmark record should include the Git revision, package version, Python version,
platform, solver and table versions, corpus identifier and hash, random seed, timing mode,
node count when available, memory measurement method, solution length metric, timeout,
and independent verification result.

Randomness must be local to a run and explicitly seeded. Benchmark output should be
machine-readable JSON Lines with a separately generated human summary. Raw results are
artifacts; curated corpora and schemas belong in version control when their licenses and
sizes permit it.

Performance comparisons must separate one-time initialization from warm solving, avoid
mixing machines in aggregate timing claims, and report failures rather than dropping them.
