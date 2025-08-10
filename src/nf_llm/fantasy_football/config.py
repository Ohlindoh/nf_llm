"""
Central configuration for fantasy football application.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Set

@dataclass
class Config:
    """Main application configuration."""
    # Paths
    DATA_DIR: str = "data"
    DATA_FILE: str = "merged_fantasy_football_data.csv"
    
    # LLM Configuration
    LLM_MODEL: str = "gpt-4"
    LLM_TEMPERATURE: float = 0.0
    OPENAI_API_KEY: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    
    # Optimization Settings
    SALARY_CAP: int = 50000
    MIN_SALARY: int = 45000
    MAX_LINEUPS: int = 150
    DEFAULT_MAX_EXPOSURE: float = 0.3
    
    # Position Settings - Using field(default_factory=lambda) for mutable defaults
    ROSTER_POSITIONS: Dict[str, int] = field(
        default_factory=lambda: {
            'QB': 1,
            'RB': 2,
            'WR': 3,
            'TE': 1,
            'DST': 1,
            'FLEX': 1
        }
    )
    
    FLEX_POSITIONS: Set[str] = field(
        default_factory=lambda: {'RB', 'WR', 'TE'}
    )
    
    # Analysis Settings
    VALUE_THRESHOLD: float = 2.0
    STACK_SALARY_THRESHOLD: float = 15000  # 30% of salary cap
    CORRELATION_BOOST: float = 0.1  # 10% boost for correlated players
    
    # Display Settings
    POSITION_DISPLAY_ORDER: list = field(
        default_factory=lambda: [
            'QB', 'RB1', 'RB2', 'WR1', 'WR2', 'WR3', 'TE', 'FLEX', 'DST'
        ]
    )
    
    @property
    def data_path(self) -> str:
        """Get full path to data file."""
        return os.path.join(self.DATA_DIR, self.DATA_FILE)
    
    @property
    def llm_config(self) -> Dict:
        """Get LLM configuration dict."""
        return {
            "config_list": [{
                "model": self.LLM_MODEL,
                "api_key": self.OPENAI_API_KEY,
                "temperature": self.LLM_TEMPERATURE
            }]
        }

    def validate(self) -> bool:
        """Validate configuration settings."""
        if not self.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not found in environment variables")
        
        if not os.path.exists(self.DATA_DIR):
            raise ValueError(f"Data directory not found: {self.DATA_DIR}")
        
        if not os.path.exists(self.data_path):
            raise ValueError(f"Data file not found: {self.data_path}")
        
        return True