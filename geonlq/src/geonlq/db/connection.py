"""Pool de conexiones SQLAlchemy para PostGIS."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from ..core.config import settings
from ..core.exceptions import DatabaseError

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Verifica conexiones antes de usarlas
    echo=settings.debug,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_db_session() -> Session:
    """Context manager que proporciona una sesión de BD con manejo de errores."""
    session = SessionLocal()
    try:
        # Configura timeout de query
        session.execute(
            text(f"SET LOCAL statement_timeout = '{settings.sql_timeout * 1000}'")
        )
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise DatabaseError(str(e)) from e
    finally:
        session.close()


def test_connection() -> bool:
    """Verifica que la conexión a la base de datos es exitosa."""
    try:
        with get_db_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
