"""
Patch services to use mock LLM for stress testing
Add this at the top of your stress test files
"""

# At the very beginning of stress_test_*.py, add:
import sys
import os

# Monkey-patch the async llm_interactions before importing anything else
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create mock module
import asyncio
from typing import AsyncGenerator

async def mock_get_model_output_async(*args, **kwargs) -> AsyncGenerator[str, None]:
    """Mock LLM that doesn't call real APIs"""
    words = "This is a mock streaming response for stress testing purposes".split()
    for word in words:
        yield word + " "
        await asyncio.sleep(0.01)  # Simulate network delay

# Patch before Django loads
import ai_model.llm_interactions_async as llm_async
llm_async.get_model_output_async = mock_get_model_output_async

# Now import and run tests...
