"""Safe extraction of `.dem` payloads from downloaded demo zip packages."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import zipfile

from ..errors import DemoInvalidError

# Competitive demos are large but finite; reject zip-bomb style members.
MAX_DEMO_BYTES = 1_073_741_824  # 1 GiB


@dataclass(frozen=True, slots=True)
class ResolvedDemo:
    """A concrete `.dem` ready for parsers, plus the user-supplied source path."""

    source_path: Path
    demo_path: Path
    size_bytes: int
    from_archive: bool
    archive_member: str | None = None


def resolve_demo_file(raw: str | Path, *, extract_root: Path) -> ResolvedDemo:
    source = validate_demo_source(raw)
    if source.suffix.lower() == ".dem":
        size = source.stat().st_size
        return ResolvedDemo(
            source_path=source,
            demo_path=source,
            size_bytes=size,
            from_archive=False,
        )
    return _extract_dem_from_zip(source, extract_root=extract_root)


def validate_demo_source(raw: str | Path) -> Path:
    """Accept a `.dem` or a `.zip` that packages a demo download."""
    path = Path(raw).expanduser()
    suffix = path.suffix.lower()
    if suffix not in {".dem", ".zip"}:
        raise DemoInvalidError("Expected a .dem file or a .zip containing a .dem.")

    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise DemoInvalidError("Demo file does not exist.") from exc

    if not resolved.is_file():
        raise DemoInvalidError("Demo path is not a regular file.")

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise DemoInvalidError("Demo file metadata could not be read.") from exc

    if size <= 0:
        raise DemoInvalidError("Demo file is empty.")

    return resolved


def _extract_dem_from_zip(zip_path: Path, *, extract_root: Path) -> ResolvedDemo:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            member_name = _select_dem_member(archive, zip_stem=zip_path.stem)
            info = archive.getinfo(member_name)
            if info.file_size <= 0:
                raise DemoInvalidError("Demo entry inside the zip is empty.")
            if info.file_size > MAX_DEMO_BYTES:
                raise DemoInvalidError(
                    "Demo entry inside the zip exceeds the maximum allowed size.",
                    details={
                        "max_bytes": MAX_DEMO_BYTES,
                        "member_size": info.file_size,
                    },
                )

            digest = hashlib.sha256()
            root = Path(extract_root)
            root.mkdir(parents=True, exist_ok=True)
            staging = root / f".staging-{zip_path.stem}-{info.CRC:08x}.dem"
            target: Path | None = None
            try:
                with archive.open(info, "r") as src, staging.open("wb") as dst:
                    remaining = info.file_size
                    while remaining > 0:
                        chunk = src.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        digest.update(chunk)
                        dst.write(chunk)
                if remaining != 0:
                    raise DemoInvalidError(
                        "Zip demo entry ended before declared size."
                    )

                sha = digest.hexdigest()
                target_dir = root / sha
                target_dir.mkdir(parents=True, exist_ok=True)
                safe_name = Path(member_name.replace("\\", "/")).name
                if not safe_name.lower().endswith(".dem"):
                    safe_name = f"{zip_path.stem}.dem"
                target = (target_dir / safe_name).resolve()
                if not str(target).startswith(str(target_dir.resolve())):
                    raise DemoInvalidError("Refusing to extract outside extract root.")
                if not target.exists():
                    staging.replace(target)
                else:
                    staging.unlink(missing_ok=True)
            finally:
                if staging.exists():
                    staging.unlink(missing_ok=True)

            assert target is not None
            size = target.stat().st_size
            if size <= 0:
                raise DemoInvalidError("Extracted demo file is empty.")

            return ResolvedDemo(
                source_path=zip_path,
                demo_path=target,
                size_bytes=size,
                from_archive=True,
                archive_member=member_name,
            )
    except DemoInvalidError:
        raise
    except zipfile.BadZipFile as exc:
        raise DemoInvalidError("The zip archive is corrupt or not a zip file.") from exc
    except OSError as exc:
        raise DemoInvalidError("Failed to read or extract the demo zip.") from exc


def _select_dem_member(archive: zipfile.ZipFile, *, zip_stem: str) -> str:
    candidates: list[str] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        _reject_unsafe_member(name)
        if Path(name).suffix.lower() == ".dem":
            candidates.append(name)

    if not candidates:
        raise DemoInvalidError("Zip archive does not contain a .dem file.")

    if len(candidates) == 1:
        return candidates[0]

    preferred = [name for name in candidates if Path(name).stem == zip_stem]
    if len(preferred) == 1:
        return preferred[0]

    raise DemoInvalidError(
        "Zip archive contains multiple .dem files; expected one match.",
        details={"members": candidates},
    )


def _reject_unsafe_member(name: str) -> None:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise DemoInvalidError("Zip member path is unsafe.")
    if any(part == ".." for part in normalized.split("/")):
        raise DemoInvalidError("Zip member path is unsafe.")
