"""Init file for pyradiko package."""

from pyradiko.exceptions import (
    RadikoAuthError,
    RadikoError,
    RadikoPlaylistError,
    RadikoProgramNotFoundError,
    RadikoRecordError,
)
from pyradiko.main import RadikoLoginAuth, RadikoRecorder
from pyradiko.metadata import embed_metadata
from pyradiko.program import Program, fetch_programs, get_program_by_time

__all__ = [
    "RadikoRecorder",
    "RadikoLoginAuth",
    "Program",
    "fetch_programs",
    "get_program_by_time",
    "embed_metadata",
    "RadikoError",
    "RadikoAuthError",
    "RadikoPlaylistError",
    "RadikoRecordError",
    "RadikoProgramNotFoundError",
]
