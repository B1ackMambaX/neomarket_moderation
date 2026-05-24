class DomainException(Exception):
    code: str = "DOMAIN_ERROR"
    status_code: int = 400


class NotFoundException(DomainException):
    code = "NOT_FOUND"
    status_code = 404


class ValidationException(DomainException):
    code = "VALIDATION_ERROR"
    status_code = 400


class ConflictException(DomainException):
    code = "CONFLICT"
    status_code = 409


class PermissionDeniedException(DomainException):
    code = "PERMISSION_DENIED"
    status_code = 403


class UpstreamServiceException(DomainException):
    code = "UPSTREAM_SERVICE_ERROR"
    status_code = 502
