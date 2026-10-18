"""Exceptions carrying the CLI exit code (spec section 10)."""


class DatasetError(Exception):
    exit_code = 1


class ValidationFailed(DatasetError):
    exit_code = 1


class RawInputError(DatasetError):
    exit_code = 2


class MappingError(DatasetError):
    exit_code = 3


class FetchError(DatasetError):
    exit_code = 4


class DiskSpaceError(DatasetError):
    exit_code = 5
