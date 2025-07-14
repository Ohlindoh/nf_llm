-- Database schema for nf_llm project

-- Dimension table for players
CREATE TABLE IF NOT EXISTS dim_player (
    player_id INTEGER PRIMARY KEY,
    player_name VARCHAR NOT NULL,
    player_position_id VARCHAR NOT NULL,
    player_team_id VARCHAR NOT NULL,
    pos_rank VARCHAR,
    rank_ecr FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimension table for slates
CREATE TABLE IF NOT EXISTS dim_slate (
    slate_id INTEGER PRIMARY KEY,
    slate_date DATE NOT NULL,
    slate_type VARCHAR NOT NULL,  -- e.g., 'main', 'showdown', etc.
    site VARCHAR NOT NULL,        -- e.g., 'draftkings', 'fanduel', etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fact table for raw projections
CREATE TABLE IF NOT EXISTS f_projection_raw (
    projection_id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    slate_id INTEGER NOT NULL,
    projected_points FLOAT NOT NULL,
    source VARCHAR NOT NULL,      -- source of the projection
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES dim_player (player_id),
    FOREIGN KEY (slate_id) REFERENCES dim_slate (slate_id)
);

-- Fact table for raw salaries
CREATE TABLE IF NOT EXISTS f_salary_raw (
    salary_id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    slate_id INTEGER NOT NULL,
    salary FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES dim_player (player_id),
    FOREIGN KEY (slate_id) REFERENCES dim_slate (slate_id)
);
