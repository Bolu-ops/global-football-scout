from collections.abc import Iterator

from sqlalchemy.orm import Session

from gfs_core.db import get_session


def db() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()
