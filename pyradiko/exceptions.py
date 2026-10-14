"""Exceptions for pyradiko."""


class RadikoError(Exception):
    """Base exception for all pyradiko errors."""


class RadikoAuthError(RadikoError, PermissionError):
    """Raised when authentication (login, auth1, or auth2) fails.

    Inherits from PermissionError for backwards compatibility.
    """


class RadikoPlaylistError(RadikoError):
    """Raised when fetching stream or playlist fails."""


class RadikoRecordError(RadikoError):
    """Raised when recording or ffmpeg command fails."""


class RadikoProgramNotFoundError(RadikoError):
    """Raised when a specified program is not found in the timetable."""
