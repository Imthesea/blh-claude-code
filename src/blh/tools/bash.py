import subprocess


def run_bash(command: str, workdir: str, timeout: int = 120, max_output: int = 30000) -> str:
    """Run a shell command in workdir and return its combined output.

    Known limitation: on timeout only the shell process is killed; grandchild
    processes spawned via shell=True may be orphaned and keep running.
    """
    try:
        proc = subprocess.run(
            command, shell=True, cwd=workdir, check=False,
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout}s"
    output = (proc.stdout or "") + (proc.stderr or "")
    if len(output) > max_output:
        output = output[:max_output] + f"\n... [truncated, {len(output)} chars total]"
    return output or f"(exit code {proc.returncode})"
