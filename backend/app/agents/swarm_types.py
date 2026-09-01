"""Swarm types and sub-agent role definitions."""

from dataclasses import dataclass, field

SUB_AGENT_ROLES = [
    {
        "name": "researcher",
        "description": "Search the web and gather current facts",
        "tools": ["web_search", "mcp_tavily_tavily_search"],
    },
    {
        "name": "analyst",
        "description": "Analyze data and break down complex problems",
        "tools": ["read_file", "list_directory"],
    },
    {
        "name": "executor",
        "description": "Run commands and write files to accomplish tasks",
        "tools": ["execute_system_command", "write_file", "run_github_code"],
    },
]


@dataclass
class SwarmResult:
    content: str
    model_name: str
    agents_used: list[str] = field(default_factory=list)
    tool_calls_made: list[str] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
