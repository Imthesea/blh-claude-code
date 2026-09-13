from pathlib import Path


def glob_files(pattern: str, workdir: str) -> str:
    root = Path(workdir)
    matches = sorted(p for p in root.glob(pattern) if p.is_file())
    if not matches:
        return "(no matches)"
    return "\n".join(str(p.relative_to(root)) for p in matches[:200])
