import subprocess
import tempfile
from pathlib import Path

from app.runtime.sandbox import resolve_in_sandbox, sandbox_workdir
from app.skills.registry import skill
from app.skills.web_search import search_web


ALLOWED_COMMANDS = {"ls", "pwd", "echo", "cat", "head", "tail", "wc", "date", "whoami"}


@skill(
    name="run_github_code",
    description=(
        "Clone a GitHub repository and run a Python script from it. "
        "Use for Claude GitHub skills or other skill repositories."
    ),
)
def run_github_code(repo_url: str, script_path: str) -> str:
    with tempfile.TemporaryDirectory(prefix="skill_") as tmpdir:
        clone_result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, tmpdir],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if clone_result.returncode != 0:
            return f"Git clone failed: {clone_result.stderr}"

        script = Path(tmpdir) / script_path
        if not script.exists():
            return f"Script not found: {script_path}"

        run_result = subprocess.run(
            ["python3", str(script)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=tmpdir,
        )
        output = run_result.stdout or run_result.stderr
        status = "Success" if run_result.returncode == 0 else f"Failed (code {run_result.returncode})"
        return f"[{status}] Output:\n{output}"


@skill(
    name="execute_system_command",
    description="Execute a safe read-only system command (ls, pwd, echo, cat, head, tail, wc, date, whoami).",
)
def execute_system_command(command: str) -> str:
    base_cmd = command.strip().split()[0] if command.strip() else ""
    if base_cmd not in ALLOWED_COMMANDS:
        return f"Command '{base_cmd}' not allowed. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=sandbox_workdir(),
        )
        output = result.stdout or result.stderr
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."


@skill(
    name="read_file",
    description="Read the contents of a file from the local filesystem (read-only, within workspace).",
)
def read_file(file_path: str) -> str:
    try:
        path = resolve_in_sandbox(file_path)
    except PermissionError:
        return "Error: Access denied. File must be within the agent sandbox."

    if not path.exists():
        return f"Error: File not found: {file_path}"

    if not path.is_file():
        return f"Error: Not a file: {file_path}"

    if path.stat().st_size > 100_000:
        return "Error: File too large (>100KB). Use head/tail commands instead."

    return path.read_text(encoding="utf-8", errors="replace")


@skill(
    name="web_search",
    description="Search the web for current information, news, documentation, or facts. Uses Tavily API or DuckDuckGo fallback.",
)
def web_search(query: str) -> str:
    return search_web(query)


@skill(
    name="list_directory",
    description="List files and directories at a given path within the workspace.",
)
def list_directory(directory_path: str) -> str:
    try:
        path = resolve_in_sandbox(directory_path)
    except PermissionError:
        return "Error: Access denied. Directory must be within the agent sandbox."

    if not path.exists():
        return f"Error: Directory not found: {directory_path}"

    entries = []
    for entry in sorted(path.iterdir()):
        prefix = "d" if entry.is_dir() else "f"
        entries.append(f"[{prefix}] {entry.name}")

    return "\n".join(entries) if entries else "(empty directory)"


@skill(
    name="write_file",
    description="Write content to a file within the workspace. Creates parent directories if needed.",
)
def write_file(file_path: str, content: str) -> str:
    try:
        path = resolve_in_sandbox(file_path)
    except PermissionError:
        return "Error: Access denied. File must be within the agent sandbox."

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} bytes to {file_path}"
