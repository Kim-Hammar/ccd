CREATE TABLE IF NOT EXISTS app_state (
    server_id  INTEGER PRIMARY KEY,
    counter    BIGINT      NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO app_state (server_id, counter)
SELECT g, 0 FROM generate_series(1, 200) AS g
ON CONFLICT (server_id) DO NOTHING;
