# Test Fixture Builders

This directory contains deterministic builders used by API tests and explicitly
named legacy compatibility fixtures. It has no developer-facing seed CLI, does
not provision users, and does not own live development scenarios.

Live upstream behavior belongs to an external development source service. The
former direct SQLite compatibility seeder has been removed.

Production code may not import `seedmaker`. Tests can opt in through the
explicit `devtools` Python path and must supply their own authenticated client
when exercising product APIs.
