"""Pool de conexiones SQLAlchemy para PostGIS (multi-escala)."""
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from ..core.config import settings
from ..core.exceptions import DatabaseError, MTDNLQException, QueryTimeoutError
from ..core.scale import database_name, parse_scale_from_database_url

_engines: dict[int, tuple] = {}


def _database_url_for_scale(scale: int) -> str:
    """Construye DATABASE_URL cambiando solo el nombre de la base (mtdN)."""
    parsed = urlparse(settings.database_url)
    db = database_name(scale)
    return urlunparse(parsed._replace(path=f"/{db}"))


def _get_engine_bundle(scale: int):
    if scale not in _engines:
        url = _database_url_for_scale(scale)
        engine = create_engine(
            url,
            pool_size=3,
            max_overflow=5,
            pool_pre_ping=True,
            echo=settings.debug,
        )
        session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        _engines[scale] = (engine, session_factory)
    return _engines[scale]


@contextmanager
def get_db_session(scale: int | None = None) -> Session:
    """Sesión de BD para la escala indicada (cada escala = base mtdN distinta)."""
    if scale is None:
        scale = parse_scale_from_database_url(settings.database_url)
    _, SessionLocal = _get_engine_bundle(scale)
    session = SessionLocal()
    try:
        session.execute(
            text(f"SET LOCAL statement_timeout = '{settings.sql_timeout * 1000}'")
        )
        yield session
        session.commit()
    except MTDNLQException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        error_msg = str(e)
        if "statement timeout" in error_msg.lower() or "canceling statement" in error_msg.lower():
            raise QueryTimeoutError(settings.sql_timeout) from e
        raise DatabaseError(str(e)) from e
    finally:
        session.close()


def test_connection(scale: int | None = None) -> bool:
    """Verifica conexión a la BD de la escala."""
    try:
        with get_db_session(scale) as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
