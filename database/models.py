"""
Database Schema for SmartFinance POS Financial Intelligence Engine
Designed to replace hardcoded provider configurations with database-driven rules.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, 
    ForeignKey, Text, JSON, Index, UniqueConstraint, CheckConstraint,
    Enum as SQLEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.sql import func
import enum


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class TransactionType(str, enum.Enum):
    WITHDRAWAL = "withdrawal"
    PURCHASE = "purchase"
    POS_TRANSFER = "pos_transfer"
    POS_QR = "pos_qr"
    TRANSFER_TO_BANK = "transfer_to_bank"
    AIRTIME = "airtime"
    DATA = "data"
    BILLS_PAYMENT = "bills_payment"


class FeeType(str, enum.Enum):
    FLAT = "flat"
    PERCENTAGE = "percentage"


class EvidenceType(str, enum.Enum):
    SCREENSHOT = "screenshot"
    PDF_STATEMENT = "pdf_statement"
    CSV_EXPORT = "csv_export"
    EXCEL_EXPORT = "excel_export"
    MANUAL_ENTRY = "manual_entry"


class EvidenceStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    REJECTED = "rejected"
    PROCESSED = "processed"


# ─────────────────────────────────────────────────────────────────────────────
# MERCHANTS
# ─────────────────────────────────────────────────────────────────────────────

class Merchant(Base):
    """
    A POS business owner. Each merchant has their own pricing, transactions,
    and financial records. Multi-tenant isolation is enforced at the application
    layer (every query filters by merchant_id).
    """
    __tablename__ = "merchants"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Provider assignment
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    merchant_level_id: Mapped[int] = mapped_column(ForeignKey("provider_levels.id"), nullable=False)
    
    # Business metadata
    business_type: Mapped[str] = mapped_column(String(100), default="POS Agent")
    location: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    provider: Mapped["Provider"] = relationship(back_populates="merchants")
    merchant_level: Mapped["ProviderLevel"] = relationship(back_populates="merchants")
    merchant_pricing: Mapped["MerchantPricing"] = relationship(
        back_populates="merchant", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    evidence: Mapped[List["Evidence"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    daily_financials: Mapped[List["DailyFinancial"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    forecasts: Mapped[List["Forecast"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    ai_insights: Mapped[List["AIInsight"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_merchant_provider_level", "provider_id", "merchant_level_id"),
    )


class MerchantPricing(Base):
    """
    What THIS merchant charges THEIR customers. Configured once at onboarding.
    Every operator prices differently — this is never hardcoded.
    
    withdrawal_brackets: JSON array of {min, max, charge}
    transfer_to_bank_brackets: JSON array of {min, max, charge}
    airtime_data_bills_charge: flat fee for airtime/data/bills_payment
    pos_transfers_qr_charge: flat fee for POS transfers/QR
    """
    __tablename__ = "merchant_pricing"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchants.id"), unique=True, nullable=False
    )
    
    # Withdrawal brackets: [{min: 1, max: 3000, charge: 100}, ...]
    withdrawal_brackets: Mapped[dict] = mapped_column(JSON, nullable=False, default={})
    
    # Transfer to bank brackets: [{min: 1, max: 3000, charge: 100}, ...]
    transfer_to_bank_brackets: Mapped[dict] = mapped_column(JSON, nullable=False, default={})
    
    # Airtime / Data / Bills: flat fee per transaction
    airtime_data_bills_charge: Mapped[float] = mapped_column(Float, default=0.0)
    
    # POS Transfers / QR: flat fee per transaction
    pos_transfers_qr_charge: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="merchant_pricing")


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDERS
# ─────────────────────────────────────────────────────────────────────────────

class Provider(Base):
    """
    A POS service provider (OPay, Moniepoint, PalmPay, etc.)
    """
    __tablename__ = "providers"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # "OPAY", "MONIEPOINT"
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    levels: Mapped[List["ProviderLevel"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    merchants: Mapped[List["Merchant"]] = relationship(back_populates="provider")


class ProviderLevel(Base):
    """
    Merchant levels within a provider (Platinum, Gold, Regular for OPay)
    """
    __tablename__ = "provider_levels"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Platinum", "Gold", "Regular"
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # "PLATINUM", "GOLD", "REGULAR"
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    provider: Mapped["Provider"] = relationship(back_populates="levels")
    merchants: Mapped[List["Merchant"]] = relationship(back_populates="merchant_level")
    pricing_rules: Mapped[List["ProviderPricingRule"]] = relationship(
        back_populates="level", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        UniqueConstraint("provider_id", "code", name="uq_provider_level_code"),
    )


class ProviderPricingRule(Base):
    """
    Provider fee schedule brackets. This is the database-driven replacement
    for the hardcoded brackets in providers/opay.py.
    
    Format matches rules.py expectations:
    - Flat fee: {min, max, type="flat", value}
    - Percentage: {min, max, type="percentage", rate, cap}
    
    max=None means open-ended (no upper bound).
    """
    __tablename__ = "provider_pricing_rules"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("provider_levels.id"), nullable=False)
    
    # Service type: withdrawal, purchase, pos_transfer, etc.
    service_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Bracket range
    min_amount: Mapped[float] = mapped_column(Float, nullable=False)
    max_amount: Mapped[Optional[float]] = mapped_column(Float)  # None = open-ended
    
    # Fee calculation
    fee_type: Mapped[str] = mapped_column(
        SQLEnum(FeeType), nullable=False
    )
    flat_value: Mapped[Optional[float]] = mapped_column(Float)  # for fee_type="flat"
    percentage_rate: Mapped[Optional[float]] = mapped_column(Float)  # for fee_type="percentage"
    percentage_cap: Mapped[Optional[float]] = mapped_column(Float)  # max fee for percentage
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Versioning / effective-dating (added by database migrate.py against the
    # real smartfinance.db; declared here so the ORM can actually see them)
    rule_version: Mapped[Optional[str]] = mapped_column(String(20), default="v1")
    effective_from: Mapped[Optional[Date]] = mapped_column(Date)
    effective_to: Mapped[Optional[Date]] = mapped_column(Date)

    # How much this specific bracket should be trusted. Not every provider's
    # schedule was established the same way - see providers/opay.py
    # ("VERIFIED... tested against every bracket value") vs.
    # providers/moniepoint.py ("PROVISIONAL... derived from a single real
    # statement's observed pairs"). confidence_source records WHY, not just
    # the level.
    confidence_level: Mapped[Optional[str]] = mapped_column(String(10), default="high")
    confidence_source: Mapped[Optional[str]] = mapped_column(String(255))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    level: Mapped["ProviderLevel"] = relationship(back_populates="pricing_rules")
    
    # Validation constraints
    __table_args__ = (
        # Ensure flat fees have a value
        CheckConstraint(
            "fee_type != 'flat' OR flat_value IS NOT NULL",
            name="chk_flat_fee_has_value"
        ),
        # Ensure percentage fees have a rate
        CheckConstraint(
            "fee_type != 'percentage' OR percentage_rate IS NOT NULL",
            name="chk_percentage_fee_has_rate"
        ),
        # Ensure min < max (when max is not None)
        CheckConstraint(
            "max_amount IS NULL OR min_amount < max_amount",
            name="chk_min_less_than_max"
        ),
        # Ensure non-negative amounts
        CheckConstraint("min_amount >= 0", name="chk_min_amount_non_negative"),
        CheckConstraint("max_amount IS NULL OR max_amount > 0", name="chk_max_amount_positive"),
        
        Index("idx_pricing_rule_lookup", "level_id", "service_type", "min_amount"),
        UniqueConstraint(
            "level_id", "service_type", "min_amount", "max_amount",
            name="uq_pricing_rule_bracket"
        ),
    )


class ProviderCashbackRule(Base):
    """
    Cashback/rewards rules (e.g., OPay Rewards Levels).
    Currently deferred — placeholder for future implementation.
    """
    __tablename__ = "provider_cashback_rules"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    
    # Rule definition (flexible JSON structure)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProviderSettlementRule(Base):
    """
    Settlement timing and rules (e.g., T+1 settlement, weekend delays).
    """
    __tablename__ = "provider_settlement_rules"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    
    # Settlement timing
    settlement_days: Mapped[int] = mapped_column(Integer, default=1)  # T+1 = 1
    weekend_delay: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Settlement fees (if any)
    settlement_fee_flat: Mapped[Optional[float]] = mapped_column(Float)
    settlement_fee_percentage: Mapped[Optional[float]] = mapped_column(Float)
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# GOVERNMENT RULES
# ─────────────────────────────────────────────────────────────────────────────

class GovernmentRule(Base):
    """
    Government levies and taxes (EMTL/Stamp Duty, VAT, etc.)
    """
    __tablename__ = "government_rules"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Rule identification
    rule_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # "EMTL", "VAT"
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Rule configuration (flexible JSON)
    # EMTL: {threshold: 10000, amount: 50, applies_to: "merchant"}
    # VAT: {rate: 0.075, applies_to: "all_transactions"}
    rule_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Effective dates
    effective_from: Mapped[Date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[Date]] = mapped_column(Date)  # None = still active
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTIONS & EVIDENCE
# ─────────────────────────────────────────────────────────────────────────────

class Evidence(Base):
    """
    Operational evidence (screenshots, PDFs, CSVs) uploaded by merchants.
    Tracks extraction status and confidence scores.
    """
    __tablename__ = "evidence"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    
    # Evidence metadata
    evidence_type: Mapped[str] = mapped_column(SQLEnum(EvidenceType), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500))  # For file storage
    file_content: Mapped[Optional[str]] = mapped_column(Text)  # Base64-encoded content for small files in DB
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # Extraction results
    status: Mapped[str] = mapped_column(
        SQLEnum(EvidenceStatus), default=EvidenceStatus.PENDING
    )
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSON)  # Raw extraction
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)  # 0.0 - 1.0
    
    # Validation
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timestamps
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="evidence")
    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )


class Transaction(Base):
    """
    Individual POS transaction. Linked to evidence (if extracted from screenshot/PDF)
    or manually entered.
    """
    __tablename__ = "transactions"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    evidence_id: Mapped[Optional[int]] = mapped_column(ForeignKey("evidence.id"))
    
    # Transaction details
    transaction_date: Mapped[Date] = mapped_column(Date, nullable=False)
    transaction_type: Mapped[str] = mapped_column(SQLEnum(TransactionType), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Provider details
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    merchant_level: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Financial breakdown (calculated by financial_engine)
    customer_charge: Mapped[float] = mapped_column(Float, nullable=False)
    provider_fee: Mapped[float] = mapped_column(Float, nullable=False)
    emtl: Mapped[float] = mapped_column(Float, default=0.0)
    profit: Mapped[float] = mapped_column(Float, nullable=False)

    # Audit / pricing comparison fields used by the ledger repository
    observed_provider_fee: Mapped[Optional[float]] = mapped_column(Float)
    calculated_provider_fee: Mapped[Optional[float]] = mapped_column(Float)
    pricing_difference: Mapped[Optional[float]] = mapped_column(Float)
    pricing_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_version: Mapped[Optional[str]] = mapped_column(String(20))
    rule_confidence_level: Mapped[Optional[str]] = mapped_column(String(10))
    
    # Reference numbers (for reconciliation)
    rrn: Mapped[Optional[str]] = mapped_column(String(100))  # Retrieval Reference Number
    terminal_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Status
    is_emtl_qualifying: Mapped[bool] = mapped_column(Boolean, default=False)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="transactions")
    evidence: Mapped["Evidence"] = relationship(back_populates="transactions")
    engine_logs: Mapped[List["EngineLog"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_transaction_merchant_date", "merchant_id", "transaction_date"),
        Index("idx_transaction_rrn", "rrn"),
    )


class EngineLog(Base):
    """
    Frozen snapshot of a transaction's engine calculation for dispute
    resolution and auditing.
    """
    __tablename__ = "engine_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_version: Mapped[Optional[str]] = mapped_column(String(20))
    customer_charge: Mapped[float] = mapped_column(Float, nullable=False)
    calculated_provider_fee: Mapped[float] = mapped_column(Float, nullable=False)
    observed_provider_fee: Mapped[Optional[float]] = mapped_column(Float)
    emtl: Mapped[float] = mapped_column(Float, nullable=False)
    net_profit: Mapped[float] = mapped_column(Float, nullable=False)
    rule_confidence_level: Mapped[Optional[str]] = mapped_column(String(10))
    calculation_timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    transaction: Mapped["Transaction"] = relationship(back_populates="engine_logs")


class DailyFinancial(Base):
    """
    Aggregated daily P&L for a merchant. One row per day.
    """
    __tablename__ = "daily_financials"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    
    # Date
    date: Mapped[Date] = mapped_column(Date, nullable=False)
    
    # Financial summary
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    provider_fees: Mapped[float] = mapped_column(Float, default=0.0)
    emtl_total: Mapped[float] = mapped_column(Float, default=0.0)
    gross_profit: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Operating expenses
    opex_total: Mapped[float] = mapped_column(Float, default=0.0)
    opex_breakdown: Mapped[Optional[dict]] = mapped_column(JSON)  # {fuel: 500, electricity: 300}
    
    # Net profit
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="daily_financials")
    
    __table_args__ = (
        UniqueConstraint("merchant_id", "date", name="uq_daily_financial_merchant_date"),
        Index("idx_daily_financial_merchant_date", "merchant_id", "date"),
    )


TransactionRecord = Transaction
EvidenceRecord = Evidence
MerchantPricingRecord = MerchantPricing
# These *Record aliases exist because pos_engine/financial_engine.py has its
# own plain-dataclass Transaction and MerchantPricing used purely for the
# fee-calculation math (never persisted). Same class names, different field
# vocabularies - importing the wrong one and constructing it with the
# other's kwargs is an easy mistake. New code should import these *Record
# names rather than the bare names, to make it obvious at the call site
# which one is in scope.


class Forecast(Base):
    """
    Financial forecasts for a merchant. Generated per-merchant, never pooled.
    """
    __tablename__ = "forecasts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    
    # Forecast metadata
    forecast_date: Mapped[Date] = mapped_column(Date, nullable=False)  # When forecast was made
    target_date: Mapped[Date] = mapped_column(Date, nullable=False)  # What month is being forecasted
    
    # Predictions
    predicted_revenue: Mapped[float] = mapped_column(Float)
    predicted_expense: Mapped[float] = mapped_column(Float)
    predicted_profit: Mapped[float] = mapped_column(Float)
    predicted_cash_balance: Mapped[Optional[float]] = mapped_column(Float)
    
    # Model metadata
    model_version: Mapped[str] = mapped_column(String(50), default="v1.0")
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="forecasts")
    
    __table_args__ = (
        UniqueConstraint("merchant_id", "forecast_date", "target_date", name="uq_forecast"),
    )


class AIInsight(Base):
    """
    AI-generated insights and recommendations for a merchant.
    """
    __tablename__ = "ai_insights"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    
    # Insight metadata
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "recommendation", "alert", "opportunity"
    priority: Mapped[str] = mapped_column(String(20), nullable=False)  # "critical", "high", "medium", "low"
    
    # Insight content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[Optional[str]] = mapped_column(Text)
    
    # Status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Relationships
    merchant: Mapped["Merchant"] = relationship(back_populates="ai_insights")
    
    __table_args__ = (
        Index("idx_ai_insight_merchant_priority", "merchant_id", "priority"),
    )