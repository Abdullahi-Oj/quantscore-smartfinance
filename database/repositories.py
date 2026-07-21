"""
Data access layer. Encapsulates all database queries.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import date, datetime
from database.models import (
    Merchant, Provider, ProviderLevel, ProviderPricingRule, DailyFinancial,
    TransactionRecord as Transaction, EvidenceRecord as Evidence,
    MerchantPricingRecord as MerchantPricing,
)


class ProviderRepository:
    """Data access for providers and their pricing rules."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_provider_by_code(self, code: str) -> Optional[Provider]:
        """Get provider by code (e.g., 'OPAY')."""
        return self.db.query(Provider).filter(
            Provider.code == code.upper(),
            Provider.is_active == True
        ).first()
    
    def get_level_by_code(self, provider_id: int, level_code: str) -> Optional[ProviderLevel]:
        """Get merchant level by code (e.g., 'PLATINUM')."""
        return self.db.query(ProviderLevel).filter(
            ProviderLevel.provider_id == provider_id,
            ProviderLevel.code == level_code.upper()
        ).first()
    
    def get_fee_schedule(
        self,
        provider_code: str,
        level_code: str,
        service_type: str
    ) -> List[dict]:
        """
        Get fee schedule brackets for a provider/level/service combination.
        Returns list of bracket dicts matching rules.py format.
        
        This is the database-backed replacement for providers.get_fee_schedule().
        """
        provider = self.get_provider_by_code(provider_code)
        if not provider:
            raise ValueError(f"Unknown provider '{provider_code}'")
        
        level = self.get_level_by_code(provider.id, level_code)
        if not level:
            raise ValueError(f"Unknown level '{level_code}' for provider '{provider_code}'")
        
        rules = self.db.query(ProviderPricingRule).filter(
            ProviderPricingRule.level_id == level.id,
            ProviderPricingRule.service_type == service_type,
            ProviderPricingRule.is_active == True
        ).order_by(ProviderPricingRule.min_amount).all()
        
        if not rules:
            raise ValueError(
                f"No pricing rules found for {provider_code}/{level_code}/{service_type}"
            )
        
        # Convert to bracket format expected by rules.py
        brackets = []
        for rule in rules:
            bracket = {
                "min": rule.min_amount,
                "max": rule.max_amount,  # None = open-ended
                "type": rule.fee_type.value,
            }
            
            if rule.fee_type.value == "flat":
                bracket["value"] = rule.flat_value
            elif rule.fee_type.value == "percentage":
                bracket["rate"] = rule.percentage_rate
                bracket["cap"] = rule.percentage_cap
            
            brackets.append(bracket)
        
        return brackets


class MerchantRepository:
    """Data access for merchants."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_merchant(self, merchant_id: int) -> Optional[Merchant]:
        """Get merchant by ID."""
        return self.db.query(Merchant).filter(
            Merchant.id == merchant_id,
            Merchant.is_active == True
        ).first()
    
    def get_merchant_pricing(self, merchant_id: int) -> Optional[MerchantPricing]:
        """Get merchant's custom pricing configuration."""
        return self.db.query(MerchantPricing).filter(
            MerchantPricing.merchant_id == merchant_id
        ).first()
    
    def create_merchant(
        self,
        name: str,
        provider_code: str,
        level_code: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        business_type: str = "POS Agent",
        location: Optional[str] = None,
    ) -> Merchant:
        """Create a new merchant with provider and level assignment."""
        provider_repo = ProviderRepository(self.db)
        
        provider = provider_repo.get_provider_by_code(provider_code)
        if not provider:
            raise ValueError(f"Unknown provider '{provider_code}'")
        
        level = provider_repo.get_level_by_code(provider.id, level_code)
        if not level:
            raise ValueError(f"Unknown level '{level_code}' for provider '{provider_code}'")
        
        merchant = Merchant(
            name=name,
            email=email,
            phone=phone,
            provider_id=provider.id,
            merchant_level_id=level.id,
            business_type=business_type,
            location=location,
        )
        
        self.db.add(merchant)
        self.db.commit()
        self.db.refresh(merchant)
        
        return merchant


class TransactionRepository:
    """Data access for transactions."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_transaction(
        self,
        merchant_id: int,
        transaction_date: date,
        transaction_type: str,
        amount: float,
        provider: str,
        merchant_level: str,
        customer_charge: float,
        provider_fee: float,
        emtl: float,
        profit: float,
        is_emtl_qualifying: bool = False,
        rrn: Optional[str] = None,
        terminal_id: Optional[str] = None,
        evidence_id: Optional[int] = None,
    ) -> Transaction:
        """Create a new transaction."""
        txn = Transaction(
            merchant_id=merchant_id,
            evidence_id=evidence_id,
            transaction_date=transaction_date,
            transaction_type=transaction_type,
            amount=amount,
            provider=provider,
            merchant_level=merchant_level,
            customer_charge=customer_charge,
            provider_fee=provider_fee,
            emtl=emtl,
            profit=profit,
            is_emtl_qualifying=is_emtl_qualifying,
            rrn=rrn,
            terminal_id=terminal_id,
        )
        
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)
        
        return txn
    
    def get_transactions_by_date(
        self,
        merchant_id: int,
        date: date
    ) -> List[Transaction]:
        """Get all transactions for a merchant on a specific date."""
        return self.db.query(Transaction).filter(
            Transaction.merchant_id == merchant_id,
            Transaction.transaction_date == date
        ).all()


class DailyFinancialRepository:
    """Data access for daily financial summaries."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def upsert_daily_financial(
        self,
        merchant_id: int,
        date: date,
        transaction_count: int,
        revenue: float,
        provider_fees: float,
        emtl_total: float,
        gross_profit: float,
        opex_total: float,
        opex_breakdown: dict,
        net_profit: float,
    ) -> DailyFinancial:
        """Create or update daily financial summary."""
        existing = self.db.query(DailyFinancial).filter(
            DailyFinancial.merchant_id == merchant_id,
            DailyFinancial.date == date
        ).first()
        
        if existing:
            # Update existing
            existing.transaction_count = transaction_count
            existing.revenue = revenue
            existing.provider_fees = provider_fees
            existing.emtl_total = emtl_total
            existing.gross_profit = gross_profit
            existing.opex_total = opex_total
            existing.opex_breakdown = opex_breakdown
            existing.net_profit = net_profit
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            daily = DailyFinancial(
                merchant_id=merchant_id,
                date=date,
                transaction_count=transaction_count,
                revenue=revenue,
                provider_fees=provider_fees,
                emtl_total=emtl_total,
                gross_profit=gross_profit,
                opex_total=opex_total,
                opex_breakdown=opex_breakdown,
                net_profit=net_profit,
            )
            self.db.add(daily)
        
        self.db.commit()
        self.db.refresh(existing or daily)
        
        return existing or daily