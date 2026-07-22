import os
import shutil
import stat
import zipfile
from pathlib import PurePosixPath


class InvalidArchive(ValueError):
    """Raised when an uploaded ZIP archive violates an extraction policy."""


ALLOWED_COMPRESSION_METHODS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}


def _validated_member_path(member, allowed_extensions):
    name = member.filename
    path = PurePosixPath(name)

    if (
            not name or '\x00' in name or '\\' in name or path.is_absolute()
            or '..' in path.parts or path == PurePosixPath('.')
            or (path.parts and path.parts[0].endswith(':'))
    ):
        raise InvalidArchive("Archive contains an unsafe member path")
    if member.flag_bits & 0x1:
        raise InvalidArchive("Encrypted archive members are not supported")
    if member.compress_type not in ALLOWED_COMPRESSION_METHODS:
        raise InvalidArchive("Archive uses an unsupported compression method")

    unix_mode = member.external_attr >> 16
    if stat.S_ISLNK(unix_mode):
        raise InvalidArchive("Archive links are not supported")
    file_type = stat.S_IFMT(unix_mode)
    if file_type and not (stat.S_ISREG(unix_mode) or stat.S_ISDIR(unix_mode)):
        raise InvalidArchive("Archive contains an unsupported special file")

    if not member.is_dir() and allowed_extensions is not None:
        extension = path.suffix.lower()
        if extension not in allowed_extensions:
            raise InvalidArchive("Archive contains an unexpected file type")

    return path


def extract_validated_zip(
        archive,
        destination,
        *,
        allowed_extensions=None,
        max_members,
        max_member_size,
        max_total_size
):
    """Validate every member, then extract regular files under destination."""
    members = archive.infolist()
    if not members:
        raise InvalidArchive("Archive is empty")
    if len(members) > max_members:
        raise InvalidArchive("Archive contains too many members")

    validated = []
    total_size = 0
    destinations = set()
    for member in members:
        path = _validated_member_path(member, allowed_extensions)
        if member.file_size > max_member_size:
            raise InvalidArchive("Archive member is too large")
        total_size += member.file_size
        if total_size > max_total_size:
            raise InvalidArchive("Archive expands beyond the permitted size")

        normalized = str(path).casefold()
        if normalized in destinations:
            raise InvalidArchive("Archive contains duplicate member paths")
        destinations.add(normalized)
        validated.append((member, path))

    extracted_files = []
    for member, path in validated:
        target = os.path.join(destination, *path.parts)
        if member.is_dir():
            os.makedirs(target, exist_ok=True)
            continue

        os.makedirs(os.path.dirname(target), exist_ok=True)
        with archive.open(member, 'r') as source, open(target, 'xb') as output:
            shutil.copyfileobj(source, output)
        extracted_files.append(target)

    return extracted_files
