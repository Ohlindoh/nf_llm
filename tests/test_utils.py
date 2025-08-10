import sys
from pathlib import Path

# Ensure src directory is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import nf_llm.collectors.utils as utils


def test_clean_player_name():
    assert utils.clean_player_name("Dalvin Cook Jr.") == "dalvincook"


def test_clean_dst_name_mapping():
    assert utils.clean_dst_name("San Francisco 49ers") == "49ers"
