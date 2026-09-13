from pathlib import Path


class PathEscapeError(Exception):
    pass


def safe_path(path: str, workdir: str) -> Path:
    root = Path(workdir).resolve()
    raw = Path(path)
    p = raw.resolve() if raw.is_absolute() else (root / path).resolve()
    if p != root and root not in p.parents:
        raise PathEscapeError(f"path escapes workdir: {path}")
    return p


def read_file(path: str, workdir: str, offset: int = 1, limit: int | None = None) -> str:
    p = safe_path(path, workdir)
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(offset - 1, 0)
    selected = lines[start:] if limit is None else lines[start:start + limit]
    return "\n".join(f"{i + start + 1}\t{line}" for i, line in enumerate(selected))


def write_file(path: str, content: str, workdir: str) -> str:
    p = safe_path(path, workdir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {p}"


def edit_file(path: str, old_text: str, new_text: str, workdir: str) -> str:
    p = safe_path(path, workdir)
    if not old_text:
        return "error: old_text must not be empty"
    text = p.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count != 1:
        return f"error: old_text occurs {count} times (must be exactly 1)"
    p.write_text(text.replace(old_text, new_text), encoding="utf-8")
    return f"edited {p}"
