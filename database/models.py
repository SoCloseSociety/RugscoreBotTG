"""SQLAlchemy models for the RugScore database."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, DateTime, JSON,
    ForeignKey, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    language = Column(String, default="en")
    alert_threshold = Column(Integer, default=50)
    created_at = Column(DateTime, default=func.now())
    last_active = Column(DateTime, default=func.now(), onupdate=func.now())
    total_scans = Column(Integer, default=0)

    watchlist = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")


class TokenAnalysis(Base):
    __tablename__ = "token_analyses"

    id = Column(Integer, primary_key=True)
    contract_address = Column(String, index=True, nullable=False)
    token_name = Column(String, nullable=True)
    token_symbol = Column(String, nullable=True)
    score_contract = Column(Float, nullable=True)
    score_liquidity = Column(Float, nullable=True)
    score_holders = Column(Float, nullable=True)
    score_dev_wallet = Column(Float, nullable=True)
    score_volume = Column(Float, nullable=True)
    score_social = Column(Float, nullable=True)
    score_metadata = Column(Float, nullable=True)
    score_smart_money = Column(Float, nullable=True)
    total_score = Column(Float, index=True, nullable=True)
    risk_label = Column(String, nullable=True)
    flags = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=True)
    analyzed_at = Column(DateTime, default=func.now())


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "contract_address", name="uq_watchlist_user_ca"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    contract_address = Column(String, nullable=False)
    last_score = Column(Float, nullable=True)
    last_checked = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="watchlist")


class DevWallet(Base):
    __tablename__ = "dev_wallets"

    id = Column(Integer, primary_key=True)
    wallet_address = Column(String, unique=True, index=True, nullable=False)
    tokens_created = Column(Integer, default=0)
    tokens_rugged = Column(Integer, default=0)
    rug_rate = Column(Float, nullable=True)
    wallet_age_days = Column(Integer, nullable=True)
    flagged = Column(Boolean, default=False)
    last_updated = Column(DateTime, default=func.now())


class SmartMoneyWallet(Base):
    __tablename__ = "smart_money_wallets"

    id = Column(Integer, primary_key=True)
    wallet_address = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, nullable=True)
    win_rate = Column(Float, nullable=True)
    source = Column(String, nullable=True)  # "gmgn_scrape", "manual", "auto_detected"
    last_updated = Column(DateTime, default=func.now())
