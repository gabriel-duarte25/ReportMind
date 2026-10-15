from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.database.base import Base
from app.models import Document  # noqa: F401 - registers the model metadata

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_settings().sqlalchemy_url
    context.configure(url=url if isinstance(url, str) else url.render_as_string(hide_password=False), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
