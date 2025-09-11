from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # user | admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    issues = relationship("Issue", back_populates="author")

class Issue(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, index=True)
    room = Column(String, nullable=False)
    cinema = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    urgency = Column(String, nullable=False, default="Non urgente")  # Non urgente | Sala ferma | Urgente
    status = Column(String, nullable=False, default="In corso")
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    author = relationship("User", back_populates="issues")
