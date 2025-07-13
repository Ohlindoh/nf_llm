"""
Agent module for fantasy football lineup generation.
Handles LLM-based user input interpretation and strategy generation.
"""

import os
from typing import Dict, Optional, List
import json
from dataclasses import dataclass
from autogen import AssistantAgent, UserProxyAgent

@dataclass
class AgentConfig:
    """Configuration for LLM agents."""
    model: str = "gpt-4"
    temperature: float = 0.0
    api_key: Optional[str] = None

    def __post_init__(self):
        self.api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found in environment variables")

    @property
    def llm_config(self) -> Dict:
        return {
            "config_list": [{
                "model": self.model,
                "api_key": self.api_key,
                "temperature": self.temperature
            }]
        }

class FantasyAgentSystem:
    """Manages LLM agents for fantasy football lineup generation."""
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self._initialize_agents()

    def _initialize_agents(self):
        """Initialize the agent system with user proxy and interpreter agents."""
        self.user_proxy = UserProxyAgent(
            name="UserProxy",
            system_message="A human user who will provide input about fantasy football lineup constraints.",
            code_execution_config=False,
        )

        self.interpreter = AssistantAgent(
            name="Interpreter",
            system_message="""You are a helpful assistant that interprets user input about fantasy football lineup constraints.
            Convert natural language into a JSON format with the following possible keys:
            - must_include: list of player names to include
            - avoid_teams: list of team abbreviations to avoid
            - stack_teams: list of team abbreviations to stack
            - player_exposure_limits: dict of player names and their maximum exposure (0-1)
            - num_lineups: integer number of lineups to generate
            - max_exposure: float between 0 and 1 for maximum player exposure
            
            Examples:
            Input: "I want Patrick Mahomes and Travis Kelce in my lineup"
            Output: {"must_include": ["patrickmahomes", "traviskelce"]}
            
            Input: "No players from the Jets or Bears"
            Output: {"avoid_teams": ["nyj", "chi"]}
            
            Input: "Stack the Chiefs offense"
            Output: {"stack_teams": ["kc"]}
            
            Input: "Generate 5 lineups with 30% max exposure"
            Output: {"num_lineups": 5, "max_exposure": 0.3}
            
            Input: "Limit Mahomes to 50% exposure"
            Output: {"player_exposure_limits": {"patrickmahomes": 0.5}}
            """,
            llm_config=self.config.llm_config
        )

        self.strategy_agent = AssistantAgent(
            name="StrategyAgent",
            system_message="""You are an expert DFS Strategy Analyst specializing in NFL lineup optimization.
            Analyze provided data and generate strategic insights considering:
            1. Value-based metrics (points per dollar, rank vs salary disparities)
            2. Game theory advantages (ownership leverage, contrarian opportunities)
            3. Stack analysis (optimal QB-WR/TE combinations, game correlations)
            4. Market inefficiencies (salary vs projection disparities)
            5. Tournament vs Cash game considerations
            
            Provide specific, actionable insights including:
            - Exact player recommendations with reasoning
            - Salary implications and constraints
            - Expected ownership impact
            - Correlation benefits
            - Risk assessment
            """,
            llm_config=self.config.llm_config
        )

    def process_user_input(self, user_input: str) -> Dict:
        """Process natural language user input into structured constraints."""
        if not user_input.strip():
            return {}

        try:
            # Reset the interpreter for fresh context
            self.interpreter.reset()
            
            # Send user input to interpreter
            self.user_proxy.send(user_input, self.interpreter, request_reply=True)
            
            # Get and parse response
            response = self.interpreter.last_message()['content']
            constraints = json.loads(response)
            
            # Validate and clean constraints
            cleaned_constraints = self._clean_constraints(constraints)
            
            return cleaned_constraints

        except json.JSONDecodeError:
            print("Error: Could not parse interpreter response")
            return {}
        except Exception as e:
            print(f"Error processing user input: {str(e)}")
            return {}

    def _clean_constraints(self, constraints: Dict) -> Dict:
        """Clean and validate constraint values."""
        cleaned = {}
        
        # Clean player names (remove spaces, lowercase)
        if 'must_include' in constraints:
            cleaned['must_include'] = [
                name.replace(' ', '').lower() 
                for name in constraints['must_include']
            ]
        
        # Clean team abbreviations
        if 'avoid_teams' in constraints:
            cleaned['avoid_teams'] = [
                team.lower() 
                for team in constraints['avoid_teams']
            ]
        
        if 'stack_teams' in constraints:
            cleaned['stack_teams'] = [
                team.lower() 
                for team in constraints['stack_teams']
            ]
        
        # Clean exposure limits
        if 'player_exposure_limits' in constraints:
            cleaned['player_exposure_limits'] = {
                name.replace(' ', '').lower(): min(float(limit), 1.0)
                for name, limit in constraints['player_exposure_limits'].items()
            }
        
        # Clean numeric values
        if 'num_lineups' in constraints:
            cleaned['num_lineups'] = max(1, int(constraints['num_lineups']))
            
        if 'max_exposure' in constraints:
            cleaned['max_exposure'] = min(float(constraints['max_exposure']), 1.0)
        
        return cleaned

    def get_strategy_insights(self, data_summary: str) -> str:
        """Generate strategy insights based on data summary."""
        try:
            self.strategy_agent.reset()
            self.user_proxy.send(
                f"Analyze this fantasy football data and provide strategic insights:\n{data_summary}", 
                self.strategy_agent, 
                request_reply=True
            )
            return self.strategy_agent.last_message()['content']
        except Exception as e:
            print(f"Error generating strategy insights: {str(e)}")
            return "Could not generate strategy insights."

    def validate_lineup(self, lineup: Dict, user_input: str) -> bool:
        """Validate if a lineup meets user-specified constraints."""
        constraints = self.process_user_input(user_input)
        
        # Check must_include constraints
        if 'must_include' in constraints:
            lineup_players = {p['player_name'].lower() for p in lineup.values()}
            if not all(player in lineup_players for player in constraints['must_include']):
                return False
        
        # Check avoid_teams constraints
        if 'avoid_teams' in constraints:
            lineup_teams = {p['team'].lower() for p in lineup.values()}
            if any(team in lineup_teams for team in constraints['avoid_teams']):
                return False
        
        return True

    def explain_lineup(self, lineup: Dict, analysis_results: Dict) -> str:
        """Generate natural language explanation of lineup choices."""
        try:
            explanation_prompt = self._build_explanation_prompt(lineup, analysis_results)
            
            self.strategy_agent.reset()
            self.user_proxy.send(explanation_prompt, self.strategy_agent, request_reply=True)
            
            return self.strategy_agent.last_message()['content']
        except Exception as e:
            print(f"Error generating lineup explanation: {str(e)}")
            return "Could not generate lineup explanation."

    def _build_explanation_prompt(self, lineup: Dict, analysis_results: Dict) -> str:
        """Build prompt for lineup explanation."""
        prompt_parts = [
            "Explain the following lineup choices considering value, stacks, and strategy:\n\n"
        ]
        
        # Add lineup details
        for pos, player in lineup.items():
            prompt_parts.append(
                f"{pos}: {player['player_name']} (${player['salary']:,}, "
                f"{player['projected_points']:.1f} pts)"
            )
        
        # Add relevant analysis results
        if analysis_results:
            prompt_parts.append("\nRelevant Analysis:")
            if 'value_plays' in analysis_results:
                prompt_parts.append("Value Plays:")
                for pos, plays in analysis_results['value_plays'].items():
                    if not plays.empty:
                        top_play = plays.iloc[0]
                        prompt_parts.append(
                            f"- {pos}: {top_play['player_name']} "
                            f"(Value: {top_play['points_per_dollar']:.2f} pts/$K)"
                        )
        
        return "\n".join(prompt_parts)