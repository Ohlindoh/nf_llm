import pandas as pd

REQUIRED_COLS = {
    "player_name",
    "player_position_id",
    "team",
    "salary",
    "projected_points",
}


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Case‑insensitive column names
    df.columns = [c.lower() for c in df.columns]

    # Accept either 'team' or 'player_team_id'
    if "team" not in df.columns and "player_team_id" in df.columns:
        df.rename(columns={"player_team_id": "team"}, inplace=True)

    # Lower‑case team strings
    if "team" in df.columns:
        df["team"] = df["team"].str.lower()

    # Clean salary strings like "$4,500"
    if "salary" in df.columns:
        df["salary"] = (
            df["salary"].astype(str).str.replace(r"[\$,]", "", regex=True).astype(float)
        )

    # Ensure numeric projected points
    if "projected_points" in df.columns:
        df["projected_points"] = pd.to_numeric(df["projected_points"], errors="coerce")

    # Remove rows with NaN values in critical columns for optimization
    critical_cols = ["projected_points", "salary"]
    existing_critical_cols = [col for col in critical_cols if col in df.columns]
    if existing_critical_cols:
        df = df.dropna(subset=existing_critical_cols)

    # Add value metric for the UI
    if "value" not in df.columns and {"projected_points", "salary"} <= set(df.columns):
        df["value"] = df["projected_points"] / df["salary"]

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return df
