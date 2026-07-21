-- Schema for the IT-system testbed database (n_{m+1}).
-- Each web-service request reads and writes a row of app_state keyed by server id.

CREATE TABLE IF NOT EXISTS app_state (
    server_id  INTEGER PRIMARY KEY,
    counter    BIGINT      NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed one row per potential server (the app upserts, so pre-seeding is optional).
INSERT INTO app_state (server_id, counter)
SELECT g, 0 FROM generate_series(1, 200) AS g
ON CONFLICT (server_id) DO NOTHING;
