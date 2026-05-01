from pathlib import Path
from typing import Iterable


_ALLOWED_LOCAL_EVIDENCE_ROOTS = (
    Path("assets") / "web_evidence",
    Path("screenshots") / "violations",
    Path("screenshots") / "accidents",
)


def allowed_local_evidence_roots(base_dir: Path | None = None) -> tuple[Path, ...]:
    root = (base_dir or Path.cwd()).absolute()
    return tuple((root / relative_root).absolute() for relative_root in _ALLOWED_LOCAL_EVIDENCE_ROOTS)


def safe_local_evidence_path(image_url: str, base_dir: Path | None = None) -> Path | None:
    if not image_url or image_url.startswith(("http://", "https://")):
        return None

    workspace = (base_dir or Path.cwd()).absolute()
    raw_candidate = Path(image_url)
    candidate = raw_candidate if raw_candidate.is_absolute() else workspace / raw_candidate
    candidate = candidate.absolute()

    for root in allowed_local_evidence_roots(workspace):
        try:
            relative_candidate = candidate.relative_to(root)
        except ValueError:
            continue

        if any(part in {"", ".", ".."} for part in relative_candidate.parts):
            return None

        if _contains_symlink(root, relative_candidate.parts):
            return None

        return candidate

    return None


def _contains_symlink(root: Path, relative_parts: Iterable[str]) -> bool:
    current = root
    if current.is_symlink():
        return True
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            return True
    return False
