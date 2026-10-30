import sys
import types

# core.py starts with LEAN's `from AlgorithmImports import *`; outside LEAN an empty module stands in for it
sys.modules.setdefault("AlgorithmImports", types.ModuleType("AlgorithmImports"))
