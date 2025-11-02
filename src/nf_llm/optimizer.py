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
        self.qb_usage = {}  # Track QB usage separately for diversity
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
        max_qb_exposure = float(constraints.get("max_qb_exposure", 0.15))  # Lower QB exposure limit
        qb_diversity_mode = constraints.get("qb_diversity_mode", "rotate")  # "rotate", "limit", or "none"
        lineups = []

        for i in range(num_lineups):
            # Update exposure constraints
            exposure_constraints = self._calculate_exposure_constraints(
                i + 1, max_exposure, max_qb_exposure, qb_diversity_mode
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
        """Generate a single scenario with random projections."""
        scenario = self.data.copy()
        
        # Add variance/floor/ceiling columns if not present
        if 'floor' not in scenario.columns:
            # Estimate floor as 70% of projection for most players
            scenario['floor'] = scenario['projected_points'] * 0.7
        if 'ceiling' not in scenario.columns:
            # Estimate ceiling as 130% of projection for most players
            scenario['ceiling'] = scenario['projected_points'] * 1.3
        if 'variance' not in scenario.columns:
            # Calculate variance as the spread between floor and ceiling
            scenario['variance'] = scenario['ceiling'] - scenario['floor']
        
        # Apply random variation to projections
        scenario["projected_points"] = scenario["projected_points"] * np.random.uniform(
            0.8, 1.2, size=len(scenario)
        )
        return scenario

    def _adjust_projections_for_strategy(self, scenario: pd.DataFrame, constraints: dict) -> pd.DataFrame:
        """Adjust player projections based on lineup strategy (cash vs GPP)."""
        adjusted = scenario.copy()
        
        # Get strategy parameters from constraints
        lineup_type = constraints.get('lineup_type', 'balanced')
        ownership_strategy = constraints.get('ownership_strategy', 'balanced')
        
        # Calculate value score (points per $1000 of salary) - REAL DATA
        adjusted['value_score'] = adjusted['projected_points'] / (adjusted['salary'] / 1000)
        
        # For CASH games - Focus on value and consistency
        if lineup_type == 'cash':
            # 1. Filter out low projection players (REAL DATA)
            # Cash games should avoid risky low-projection plays
            for pos in adjusted['player_position_id'].unique():
                pos_players = adjusted[adjusted['player_position_id'] == pos]
                if len(pos_players) > 5:
                    # Remove bottom 25% of projections at each position
                    min_projection = pos_players['projected_points'].quantile(0.25)
                    adjusted = adjusted[
                        (adjusted['player_position_id'] != pos) | 
                        (adjusted['projected_points'] >= min_projection)
                    ]
            
            # 2. Boost high-value plays significantly (REAL DATA)
            # Cash games love value - normalize and apply bonus
            value_mean = adjusted['value_score'].mean()
            value_std = adjusted['value_score'].std()
            if value_std > 0:
                value_z_score = (adjusted['value_score'] - value_mean) / value_std
                # Players with good value get up to 20% boost
                value_multiplier = 1 + (value_z_score.clip(-1, 2) * 0.1)
                adjusted['strategy_score'] = adjusted['projected_points'] * value_multiplier
            else:
                adjusted['strategy_score'] = adjusted['projected_points']
            
            # 3. Penalize very expensive players in cash (REAL DATA)
            # Cash games often avoid paying up for studs
            salary_threshold = adjusted['salary'].quantile(0.85)
            expensive_mask = adjusted['salary'] > salary_threshold
            adjusted.loc[expensive_mask, 'strategy_score'] *= 0.9
            
            # 4. Minimum projection threshold for cash (REAL DATA)
            # Don't play anyone projecting under 5 points
            adjusted = adjusted[adjusted['projected_points'] >= 5.0]
            
        # For GPP - Embrace ceiling and differentiation
        elif lineup_type == 'gpp':
            # 1. GPP can play anyone (no filtering)
            adjusted['strategy_score'] = adjusted['projected_points'].copy()
            
            # 2. Ownership-based adjustments (REAL DATA)
            if ownership_strategy == 'contrarian':
                # Fade the obvious value plays
                value_mean = adjusted['value_score'].mean()
                value_std = adjusted['value_score'].std()
                if value_std > 0:
                    value_z_score = (adjusted['value_score'] - value_mean) / value_std
                    # High value = likely high owned = fade in GPP
                    ownership_penalty = value_z_score.clip(0, 2) * 0.1
                    adjusted['strategy_score'] *= (1 - ownership_penalty)
                
                # Boost low-salary dart throws
                salary_threshold = adjusted['salary'].quantile(0.25)
                cheap_mask = adjusted['salary'] < salary_threshold
                adjusted.loc[cheap_mask, 'strategy_score'] *= 1.15
            
            # 3. Boost high-upside expensive plays (REAL DATA)
            # GPPs need ceiling, expensive players often have it
            elite_threshold = adjusted['salary'].quantile(0.90)
            elite_mask = adjusted['salary'] > elite_threshold
            adjusted.loc[elite_mask, 'strategy_score'] *= 1.1
            
            # 4. Don't penalize low projections - GPPs need variance
            # Keep all players available for GPP dart throws
            
        # Balanced approach
        else:
            # Simple value adjustment
            value_mean = adjusted['value_score'].mean()
            value_std = adjusted['value_score'].std()
            if value_std > 0:
                value_z_score = (adjusted['value_score'] - value_mean) / value_std
                value_multiplier = 1 + (value_z_score.clip(-1, 1) * 0.05)
                adjusted['strategy_score'] = adjusted['projected_points'] * value_multiplier
            else:
                adjusted['strategy_score'] = adjusted['projected_points']
        
        # Apply any explicit constraints
        min_points = constraints.get('min_projected_points', 0)
        if min_points > 0:
            adjusted = adjusted[adjusted['projected_points'] >= min_points]
        
        max_salary = constraints.get('max_salary_per_player', float('inf'))
        if max_salary < float('inf'):
            adjusted = adjusted[adjusted['salary'] <= max_salary]
            
        return adjusted

    def _optimize_single_scenario(
        self, scenario: pd.DataFrame, constraints: dict
    ) -> dict | None:
        """Optimize a single scenario with given constraints."""
        try:
            print("Starting scenario optimization...")
            
            # Adjust projections based on strategy
            scenario = self._adjust_projections_for_strategy(scenario, constraints)
            
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

            # Objective function: Use strategy_score if available, otherwise projected_points
            prob += pulp.lpSum(
                p.get("strategy_score", p["projected_points"])
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
                
                # Track QB usage separately for better diversity control
                if position == "QB":
                    self.qb_usage[player_name] = (
                        self.qb_usage.get(player_name, 0) + 1
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
                
        # Add QB diversity constraints
        if "avoid_qbs" in constraints:
            for qb_name in constraints["avoid_qbs"]:
                prob += (
                    pulp.lpSum(
                        base_vars[p["player_name"], p["player_position_id"]]
                        for p in players
                        if p["player_name"] == qb_name and p["player_position_id"] == "QB"
                    )
                    == 0
                )
                
        # Force specific QB if in rotation mode
        if "force_qb" in constraints:
            qb_name = constraints["force_qb"]
            prob += (
                pulp.lpSum(
                    base_vars[p["player_name"], p["player_position_id"]]
                    for p in players
                    if p["player_name"] == qb_name and p["player_position_id"] == "QB"
                )
                == 1
            )

    def _calculate_exposure_constraints(
        self, current_lineup_count: int, max_exposure: float, max_qb_exposure: float = 0.15, qb_diversity_mode: str = "limit"
    ) -> dict:
        """Calculate exposure-based constraints for the next lineup."""
        constraints = {"avoid_players": [], "avoid_qbs": []}

        if current_lineup_count > 1:
            # Regular player exposure limits
            for player_name, count in self.player_usage.items():
                if count / current_lineup_count >= max_exposure:
                    constraints["avoid_players"].append(player_name)
            
            # Special QB exposure handling
            if qb_diversity_mode == "rotate":
                # In rotate mode, force different QBs each time until we've used many
                # Get list of all QBs in data
                all_qbs = self.data[self.data["player_position_id"] == "QB"]["player_name"].unique()
                unused_qbs = [qb for qb in all_qbs if qb not in self.qb_usage]
                
                if unused_qbs:
                    # If we have unused QBs, avoid all used QBs to force a new one
                    constraints["avoid_qbs"] = list(self.qb_usage.keys())
                else:
                    # If all QBs have been used, find the least used ones
                    if self.qb_usage:
                        min_usage = min(self.qb_usage.values())
                        # Avoid QBs that have been used more than minimum
                        for qb_name, count in self.qb_usage.items():
                            if count > min_usage:
                                constraints["avoid_qbs"].append(qb_name)
                                
            elif qb_diversity_mode == "limit":
                # In limit mode, strictly enforce max QB exposure
                for qb_name, count in self.qb_usage.items():
                    if count / current_lineup_count >= max_qb_exposure:
                        constraints["avoid_qbs"].append(qb_name)
            
            # Remove QB names from general avoid_players if they're in avoid_qbs
            # to prevent double-constraining
            constraints["avoid_players"] = [
                p for p in constraints["avoid_players"] 
                if p not in constraints["avoid_qbs"]
            ]

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

            if pos in self.settings.POSITIONS and is_selected(base_vars[name, pos]):
                if pos in position_counts:
                    position_counts[pos] += 1
                    lineup[f"{pos}{position_counts[pos]}"] = player
                else:
                    lineup[pos] = player
                used_players.add(name)

         # Then handle FLEX position - collect ALL candidates to avoid iteration order bias
        flex_candidates = []
        for player in players:
            name = player["player_name"]
            pos = player["player_position_id"]

            if name in used_players:
                continue

            if pos in self.settings.FLEX_POSITIONS and is_selected(
                flex_vars[name, pos]
            ):
                flex_candidates.append(player)

        # Select the actual FLEX player the optimizer chose (highest projected points)
        if flex_candidates:
            best_flex = max(flex_candidates, key=lambda p: float(p["projected_points"]))
            lineup["FLEX"] = best_flex
            used_players.add(best_flex["player_name"])

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
