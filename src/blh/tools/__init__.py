from ..core.config import Config
from . import bash as bash_mod
from . import files as files_mod
from . import glob as glob_mod
from .registry import Tool, ToolRegistry


def register_builtin_tools(registry: ToolRegistry, config: Config) -> None:
    wd = config.workdir
    timeout = config.bash_timeout
    max_output = config.max_output_chars
    registry.register(Tool(
        name="bash",
        description="Run a shell command in the workdir. Returns stdout+stderr.",
        parameters={"type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"]},
        handler=lambda command: bash_mod.run_bash(
            command, wd, timeout, max_output),
    ))
    registry.register(Tool(
        name="read_file",
        description="Read a file with line numbers. offset/limit select a line range.",
        parameters={"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "offset": {"type": "integer"},
                                   "limit": {"type": "integer"}},
                    "required": ["path"]},
        handler=lambda path, offset=1, limit=None: files_mod.read_file(path, wd, offset, limit),
    ))
    registry.register(Tool(
        name="write_file",
        description="Write content to a file, creating parent directories.",
        parameters={"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "content": {"type": "string"}},
                    "required": ["path", "content"]},
        handler=lambda path, content: files_mod.write_file(path, content, wd),
    ))
    registry.register(Tool(
        name="edit_file",
        description="Replace old_text with new_text. old_text must occur exactly once.",
        parameters={"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "old_text": {"type": "string"},
                                   "new_text": {"type": "string"}},
                    "required": ["path", "old_text", "new_text"]},
        handler=lambda path, old_text, new_text: files_mod.edit_file(path, old_text, new_text, wd),
    ))
    registry.register(Tool(
        name="glob",
        description="Find files matching a glob pattern, relative to workdir.",
        parameters={"type": "object",
                    "properties": {"pattern": {"type": "string"}},
                    "required": ["pattern"]},
        handler=lambda pattern: glob_mod.glob_files(pattern, wd),
    ))
