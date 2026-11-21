"""HTTP errors used across routers. All responses keep FastAPI's `{"detail": ...}` shape."""

from fastapi import HTTPException, status


def not_found(what: str) -> HTTPException:
    """For resources inside a team the caller can read. (Unreadable teams are a 403, see auth.deps.)"""
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def conflict(detail: str | dict[str, object]) -> HTTPException:
    """The request is valid but the resource's current state doesn't allow it."""
    return HTTPException(status.HTTP_409_CONFLICT, detail=detail)


def unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail=detail)


def version_conflict(current: int) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail={"message": "Changed by someone else since you loaded it", "current_version": current},
    )


COMMON_ERRORS: dict[int | str, dict[str, str]] = {
    401: {"description": "Missing, invalid or expired session"},
    403: {"description": "No access to this team, or the action needs a role the user doesn't have"},
}
