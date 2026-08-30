CREATE INDEX IF NOT EXISTS ix_upstream_mock_inspections_publication_cursor
ON upstream_mock_inspections (state, published_at, inspection_time, wafer_key);
