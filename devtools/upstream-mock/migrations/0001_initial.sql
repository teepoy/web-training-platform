CREATE TABLE IF NOT EXISTS upstream_mock_clock (
    id SMALLINT PRIMARY KEY,
    next_change_token BIGINT NOT NULL,
    CONSTRAINT ck_upstream_mock_clock_singleton CHECK (id = 1),
    CONSTRAINT ck_upstream_mock_clock_positive_token CHECK (next_change_token > 0)
);

INSERT INTO upstream_mock_clock (id, next_change_token)
VALUES (1, 1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS upstream_mock_inspections (
    wafer_key BIGINT NOT NULL,
    inspection_time TIMESTAMPTZ NOT NULL,
    lot_id VARCHAR(50) NOT NULL,
    wafer_id VARCHAR(50) NOT NULL,
    layer_id VARCHAR(50) NOT NULL,
    device VARCHAR(50) NOT NULL,
    inspect_equip_id VARCHAR(50) NOT NULL,
    recipe_key BIGINT NOT NULL,
    recipe_id VARCHAR(50) NOT NULL,
    origin_index_x INTEGER NOT NULL,
    origin_index_y INTEGER NOT NULL,
    center_x INTEGER NOT NULL,
    center_y INTEGER NOT NULL,
    origin_x INTEGER NOT NULL,
    origin_y INTEGER NOT NULL,
    die_size_x INTEGER NOT NULL,
    die_size_y INTEGER NOT NULL,
    state VARCHAR(16) NOT NULL,
    published_at TIMESTAMPTZ,
    last_updated_at TIMESTAMPTZ,
    change_token BIGINT,
    CONSTRAINT upstream_mock_inspections_pkey PRIMARY KEY (wafer_key, inspection_time),
    CONSTRAINT uq_upstream_mock_inspection_change_token UNIQUE (change_token),
    CONSTRAINT ck_upstream_mock_inspection_state CHECK (state IN ('draft', 'published')),
    CONSTRAINT ck_upstream_mock_inspection_publication_fields CHECK (
        (state = 'draft' AND published_at IS NULL AND last_updated_at IS NULL AND change_token IS NULL)
        OR
        (state = 'published' AND published_at IS NOT NULL AND last_updated_at IS NOT NULL AND change_token IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_upstream_mock_inspections_published_time
ON upstream_mock_inspections (state, inspection_time);

CREATE TABLE IF NOT EXISTS upstream_mock_defects (
    wafer_key BIGINT NOT NULL,
    inspection_time TIMESTAMPTZ NOT NULL,
    defect_id BIGINT NOT NULL,
    test_id INTEGER NOT NULL,
    class_number INTEGER NOT NULL,
    rough_bin INTEGER NOT NULL,
    wafer_x INTEGER NOT NULL,
    wafer_y INTEGER NOT NULL,
    index_x INTEGER NOT NULL,
    index_y INTEGER NOT NULL,
    adder INTEGER NOT NULL,
    cluster INTEGER NOT NULL,
    images INTEGER NOT NULL,
    size_x INTEGER NOT NULL,
    size_y INTEGER NOT NULL,
    size_d INTEGER NOT NULL,
    area INTEGER NOT NULL,
    final_bin INTEGER NOT NULL,
    manual_bin INTEGER NOT NULL,
    kill_ratio DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (wafer_key, inspection_time, defect_id),
    FOREIGN KEY (wafer_key, inspection_time)
        REFERENCES upstream_mock_inspections (wafer_key, inspection_time)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS upstream_mock_review_images (
    wafer_key BIGINT NOT NULL,
    inspection_time TIMESTAMPTZ NOT NULL,
    defect_id BIGINT NOT NULL,
    image_id BIGINT NOT NULL,
    image_type VARCHAR(50) NOT NULL,
    image_filespec VARCHAR(1024) NOT NULL,
    PRIMARY KEY (wafer_key, inspection_time, defect_id, image_id),
    FOREIGN KEY (wafer_key, inspection_time)
        REFERENCES upstream_mock_inspections (wafer_key, inspection_time)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS upstream_mock_patch_archives (
    wafer_key BIGINT NOT NULL,
    inspection_time TIMESTAMPTZ NOT NULL,
    archive_id BIGINT NOT NULL,
    s3_bucket VARCHAR(255) NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    PRIMARY KEY (wafer_key, inspection_time, archive_id),
    CONSTRAINT uq_upstream_mock_patch_archive_object
        UNIQUE (wafer_key, inspection_time, s3_bucket, s3_key),
    FOREIGN KEY (wafer_key, inspection_time)
        REFERENCES upstream_mock_inspections (wafer_key, inspection_time)
        ON DELETE CASCADE
);
