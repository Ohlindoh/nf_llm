"""
Lineup optimization logic for fantasy football.
Handles lineup generation, constraints, and optimization strategies.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pulp


@dataclass
class LineupSettings:
    """Settings for lineup optimization."""

    SALARY_CAP: int = 50000
    ROSTER_SIZE: int = 9
    POSITIONS: dict[str, int] = field(
        default_factory=lambda: {
            "QB": 1,
            "RB": 2,
            "WR": 3,
            "TE": 1,
            "DST": 1,
            "FLEX": 1,
        }
    )
    FLEX_POSITIONS: set[str] = field(default_factory=lambda: {"RB", "WR", "TE"})
    MIN_SALARY: int = 45000  # Ensure lineups aren't too cheap


class LineupOptimizer:
    """Handles DFS lineup optimization and generation."""

    def __init__(self, data: pd.DataFrame, settings: LineupSettings | None = None):
        self.data = data
        self.settings = settings or LineupSettings()
        self.previous_lineups = []
        self.player_usage = {}
        self.strategy_boost = {}
        self._validate_data()

    def _validate_data(self):
        """Ensure data has required columns and correct types."""
        required_columns = {
            "player_name",
            "player_position_id",
            "team",
            "salary",
            "projected_points",
        }
        missing = required_columns - set(self.data.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Ensure numeric types
        self.data["salary"] = pd.to_numeric(self.data["salary"])
        self.data["projected_points"] = pd.to_numeric(self.data["projected_points"])

    def generate_lineups(self, constraints: dict) -> list[dict]:
        """Generate multiple optimized lineups with exposure limits."""
        num_lineups = int(constraints.get("num_lineups", 1))
        max_exposure = float(constraints.get("max_exposure", 0.3))
        lineups = []

        for i in range(num_lineups):
            # Update exposure constraints
            exposure_constraints = self._calculate_exposure_constraints(
                i + 1, max_exposure
            )
            current_constraints = {**constraints, **exposure_constraints}

            # Generate lineup
            lineup = self.generate_lineup(current_constraints)
            if "error" in lineup:
                break

            # Update player usage tracking
            self._update_player_usage(lineup)
            lineups.append(lineup)

        return lineups

    def generate_lineup(self, constraints: dict = None) -> dict:
        """Generate a single optimized lineup based on constraints."""
        print("Starting lineup generation...")

        # Use adaptive scenario generation with convergence detection
        max_scenarios = 100
        min_scenarios = 25
        convergence_threshold = 0.01  # 1% improvement threshold

        lineups = []
        scores = []
        best_score = 0
        scenarios_without_improvement = 0

        for scenario_idx in range(max_scenarios):
            # Generate single scenario
            scenario = self._generate_single_scenario()

            if scenario_idx % 10 == 0:
                print(f"Processing scenario {scenario_idx + 1}, best score so far: {best_score:.2f}")

            lineup = self._optimize_single_scenario(scenario, constraints or {})
            if lineup:
                score = self._get_lineup_score(lineup)
                lineups.append(lineup)
                scores.append(score)

                # Check for convergence
                if score > best_score * (1 + convergence_threshold):
                    best_score = score
                    scenarios_without_improvement = 0
                    print(f"New best score: {score:.2f} at scenario {scenario_idx + 1}")
                else:
                    scenarios_without_improvement += 1

                # Early stopping if we've found enough good solutions
                if (scenario_idx >= min_scenarios and
                    scenarios_without_improvement >= 15 and
                    len(lineups) >= 5):
                    print(f"Converged after {scenario_idx + 1} scenarios (no improvement for 15 iterations)")
                    break

        print(f"Completed optimization with {len(lineups)} valid lineups from {scenario_idx + 1} scenarios")

        if not lineups:
            return {"error": "No valid lineup found"}

        # Get unique lineups
        unique_lineups = []
        unique_scores = []
        seen_combinations = set()

        for lineup, score in zip(lineups, scores, strict=False):
            players = frozenset(player["player_name"] for player in lineup.values())
            if players not in seen_combinations:
                seen_combinations.add(players)
                unique_lineups.append(lineup)
                unique_scores.append(score)

        print(f"Found {len(unique_lineups)} unique lineups")

        # Return the best unique lineup
        best_idx = unique_scores.index(max(unique_scores))
        best_score = unique_scores[best_idx]
        print(f"Selected best lineup with score: {best_score}")

        return unique_lineups[best_idx]

    def _generate_single_scenario(self) -> pd.DataFrame:
        """Generate a single scenario for optimization."""
        scenario = self.data.copy()

        # Add random noise to projected points (10% standard deviation)
        noise = np.random.normal(1, 0.1, size=len(scenario))

        # Apply position-specific adjustments
        position_multipliers = (
            scenario["player_position_id"]
            .map(
                {
                    "TE": 0.95,  # Slightly lower TE projections
                    "RB": 1.02,  # Slightly higher RB projections
                    "WR": 1.02,  # Slightly higher WR projections
                    "QB": 1.0,  # Keep QB as is
                    "DST": 1.0,  # Keep DST as is
                }
            )
            .fillna(1.0)
        )

        # Apply strategy boosts from analysis
        strategy_boosts = pd.Series(
            [
                self.strategy_boost.get(name, 0)
                for name in scenario["player_name"]
            ],
            index=scenario.index,
        )

        # Combine all adjustments
        total_multiplier = noise * position_multipliers * (1 + strategy_boosts)
        scenario["projected_points"] = (
            scenario["projected_points"] * total_multiplier
        )

        return scenario

    def apply_strategy_adjustments(self, analysis_results: dict):
        """Apply strategy-based adjustments to player projections."""
        self.strategy_boost = {}

        # Value plays boost
        if "value_plays" in analysis_results:
            for position, plays in analysis_results["value_plays"].items():
                for play in plays:  # plays is now a list of dictionaries
                    boost = min(play["points_zscore"] * 0.1, 0.15)  # Cap at 15%
                    self.strategy_boost[play["player_name"]] = max(
                        self.strategy_boost.get(play["player_name"], 0), boost
                    )

        # Stack consideration
        if "stacks" in analysis_results:
            for stack in analysis_results["stacks"][:5]:  # Top 5 stacks
                qb_boost = 0.1  # 10% boost for QB in top stack
                receiver_boost = 0.08  # 8% boost for receiver in top stack

                self.strategy_boost[stack["qb"]] = max(
                    self.strategy_boost.get(stack["qb"], 0), qb_boost
                )
                self.strategy_boost[stack["receiver"]] = max(
                    self.strategy_boost.get(stack["receiver"], 0), receiver_boost
                )

    def _optimize_single_scenario(
        self, scenario: pd.DataFrame, constraints: dict
    ) -> dict | None:
        """Optimize a single scenario with given constraints."""
        try:
            print("Starting scenario optimization...")
            prob = pulp.LpProblem("Fantasy_Football", pulp.LpMaximize)

            # Create decision variables
            players = scenario.to_dict("records")
            print(f"Processing {len(players)} players")

            base_vars = pulp.LpVariable.dicts(
                "players",
                ((p["player_name"], p["player_position_id"]) for p in players),
                cat="Binary",
            )

            flex_vars = pulp.LpVariable.dicts(
                "flex",
                (
                    (p["player_name"], p["player_position_id"])
                    for p in players
                    if p["player_position_id"] in self.settings.FLEX_POSITIONS
                ),
                cat="Binary",
            )

            # Objective function: Maximize projected points
            prob += pulp.lpSum(
                p["projected_points"]
                * (
                    base_vars[p["player_name"], p["player_position_id"]]
                    + (
                        flex_vars.get((p["player_name"], p["player_position_id"]), 0)
                        if p["player_position_id"] in self.settings.FLEX_POSITIONS
                        else 0
                    )
                )
                for p in players
            )

            print("Adding constraints...")
            self._add_constraints(prob, base_vars, flex_vars, players, constraints)

            print("Solving optimization problem...")
            prob.solve(pulp.PULP_CBC_CMD(msg=False))

            if pulp.LpStatus[prob.status] == "Optimal":
                print(
                    f"Found optimal solution with status: {pulp.LpStatus[prob.status]}"
                )
                lineup = self._build_lineup_from_solution(base_vars, flex_vars, players)
                if self._validate_lineup(lineup):
                    print(
                        f"Built valid lineup with {len(lineup)} players"
                    )
                    return lineup
                else:
                    print("Built lineup failed validation")
                    return None
            else:
                print(
                    f"No optimal solution found. Status: {pulp.LpStatus[prob.status]}"
                )
                return None

        except Exception as e:
            print(f"Error in optimization: {str(e)}")
            return None

    def _validate_lineup(self, lineup: dict) -> bool:
        """Validate that the lineup meets all basic requirements."""
        if not lineup:
            return False

        # Check we have the right number of players
        if len(lineup) != self.settings.ROSTER_SIZE:
            print(f"Invalid roster size: {len(lineup)}")
            return False

        # Verify we have all required positions
        required_positions = {
            "QB",
            "RB1",
            "RB2",
            "WR1",
            "WR2",
            "WR3",
            "TE",
            "FLEX",
            "DST",
        }
        if not all(pos in lineup for pos in required_positions):
            print(f"Missing positions: {required_positions - set(lineup.keys())}")
            return False

        # Check salary cap
        total_salary = sum(float(player["salary"]) for player in lineup.values())
        if total_salary > self.settings.SALARY_CAP:
            print(f"Salary cap exceeded: {total_salary}")
            return False
        if total_salary < self.settings.MIN_SALARY:
            print(f"Salary too low: {total_salary}")
            return False

        return True

    def _update_player_usage(self, lineup: dict):
        """Track player usage across lineups."""
        if not lineup:
            return

        for position, player in lineup.items():
            if player:
                player_name = player["player_name"]
                self.player_usage[player_name] = (
                    self.player_usage.get(player_name, 0) + 1
                )

        # Also add the lineup to our previous lineups list for reference
        self.previous_lineups.append(lineup)

    def _add_constraints(self, prob, base_vars, flex_vars, players, constraints):
        """Add all optimization constraints."""
        # Salary cap (including FLEX)
        prob += (
            pulp.lpSum(
                p["salary"]
                * (
                    base_vars[p["player_name"], p["player_position_id"]]
                    + (
                        flex_vars.get((p["player_name"], p["player_position_id"]), 0)
                        if p["player_position_id"] in self.settings.FLEX_POSITIONS
                        else 0
                    )
                )
                for p in players
            )
            <= self.settings.SALARY_CAP
        )

        # Minimum salary requirement
        prob += (
            pulp.lpSum(
                p["salary"]
                * (
                    base_vars[p["player_name"], p["player_position_id"]]
                    + (
                        flex_vars.get((p["player_name"], p["player_position_id"]), 0)
                        if p["player_position_id"] in self.settings.FLEX_POSITIONS
                        else 0
                    )
                )
                for p in players
            )
            >= self.settings.MIN_SALARY
        )

        # Base position requirements
        for pos, limit in self.settings.POSITIONS.items():
            if pos != "FLEX":
                prob += (
                    pulp.lpSum(
                        base_vars[p["player_name"], p["player_position_id"]]
                        for p in players
                        if p["player_position_id"] == pos
                    )
                    == limit
                )

        # FLEX position constraint
        prob += (
            pulp.lpSum(
                flex_vars[p["player_name"], p["player_position_id"]]
                for p in players
                if p["player_position_id"] in self.settings.FLEX_POSITIONS
            )
            == 1
        )

        # Player can't be in both base and FLEX
        for p in players:
            if p["player_position_id"] in self.settings.FLEX_POSITIONS:
                prob += (
                    base_vars[p["player_name"], p["player_position_id"]]
                    + flex_vars[p["player_name"], p["player_position_id"]]
                    <= 1
                )

        # Add user constraints
        self._add_user_constraints(prob, base_vars, flex_vars, players, constraints)

    def _add_user_constraints(self, prob, base_vars, flex_vars, players, constraints):
        """Add user-specified constraints."""
        if "must_include" in constraints:
            for player_name in constraints["must_include"]:
                prob += (
                    pulp.lpSum(
                        base_vars[p["player_name"], p["player_position_id"]]
                        + (
                            flex_vars.get(
                                (p["player_name"], p["player_position_id"]), 0
                            )
                            if p["player_position_id"] in self.settings.FLEX_POSITIONS
                            else 0
                        )
                        for p in players
                        if p["player_name"] == player_name
                    )
                    == 1
                )

        if "avoid_teams" in constraints:
            for team in constraints["avoid_teams"]:
                prob += (
                    pulp.lpSum(
                        base_vars[p["player_name"], p["player_position_id"]]
                        + (
                            flex_vars.get(
                                (p["player_name"], p["player_position_id"]), 0
                            )
                            if p["player_position_id"] in self.settings.FLEX_POSITIONS
                            else 0
                        )
                        for p in players
                        if p["team"].lower() == team.lower()
                    )
                    == 0
                )

        if "avoid_players" in constraints:
            for player_name in constraints["avoid_players"]:
                prob += (
                    pulp.lpSum(
                        base_vars[p["player_name"], p["player_position_id"]]
                        + (
                            flex_vars.get(
                                (p["player_name"], p["player_position_id"]), 0
                            )
                            if p["player_position_id"] in self.settings.FLEX_POSITIONS
                            else 0
                        )
                        for p in players
                        if p["player_name"] == player_name
                    )
                    == 0
                )

    def _calculate_exposure_constraints(
        self, current_lineup_count: int, max_exposure: float
    ) -> dict:
        """Calculate exposure-based constraints for the next lineup."""
        constraints = {"avoid_players": []}

        if current_lineup_count > 1:
            for player_name, count in self.player_usage.items():
                if count / current_lineup_count >= max_exposure:
                    constraints["avoid_players"].append(player_name)

        return constraints

    def _build_lineup_from_solution(
        self, base_vars, flex_vars, players: list[dict]
    ) -> dict:
        """Convert optimization solution to a lineup dictionary."""
        lineup = {}

        # Helper function to check if a variable is selected
        def is_selected(var):
            try:
                return var.varValue > 0.5
            except:
                return False

        # Track used players to avoid duplicates
        used_players = set()

        # First, fill the base positions
        position_counts = {"RB": 0, "WR": 0}

        for player in players:
            name = player["player_name"]
            pos = player["player_position_id"]

            if name in used_players:
                continue

            if is_selected(base_vars[name, pos]):
                if pos in ["QB", "TE", "DST"]:
                    lineup[pos] = player
                    used_players.add(name)
                elif pos in ["RB", "WR"]:
                    position_counts[pos] += 1
                    lineup[f"{pos}{position_counts[pos]}"] = player
                    used_players.add(name)

        # Then handle FLEX position
        for player in players:
            name = player["player_name"]
            pos = player["player_position_id"]

            if name in used_players:
                continue

            if pos in self.settings.FLEX_POSITIONS and is_selected(
                flex_vars[name, pos]
            ):
                lineup["FLEX"] = player
                used_players.add(name)
                break

        print(f"Built lineup with {len(lineup)} players")
        return lineup

    def _get_lineup_score(self, lineup: dict) -> float:
        """Calculate the total projected score for a lineup."""
        return sum(float(player["projected_points"]) for player in lineup.values())

    def get_player_exposure(self, player_name: str) -> float:
        """Get the exposure percentage for a specific player."""
        if not self.previous_lineups:
            return 0.0
        count = self.player_usage.get(player_name, 0)
        return count / len(self.previous_lineups)

    def get_lineup_correlation(self, lineup: dict) -> float:
        """Calculate the correlation score for a lineup."""
        team_counts = {}
        for player in lineup.values():
            team_counts[player["team"]] = team_counts.get(player["team"], 0) + 1

        correlation_score = sum(count * (count - 1) for count in team_counts.values())
        return correlation_score / len(lineup)
