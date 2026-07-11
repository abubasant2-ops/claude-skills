from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.models.enums import UserRole


class User(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "users"
    __table_args__ = (enum_check("role", UserRole),)

    role: Mapped[str] = mapped_column(String(16), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ar")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    children: Mapped[list["Child"]] = relationship(  # noqa: F821
        back_populates="guardian", foreign_keys="Child.guardian_id"
    )
