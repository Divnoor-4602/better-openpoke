"""Agent assets package.

Contains agent-specific prompts and tool registries that can be wired into
OpenRouter/OpenAI chat completion requests.
"""

from . import execution_agent, interaction_agent

__all__ = ["interaction_agent", "execution_agent"]

