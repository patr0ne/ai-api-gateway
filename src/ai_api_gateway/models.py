"""SQLAlchemy models for persistent gateway state."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata used by application queries and Alembic."""


class ApiClient(Base):
    """A client allowed to authenticate with a fingerprinted API key."""

    __tablename__ = "api_clients"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    key_fingerprint: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
