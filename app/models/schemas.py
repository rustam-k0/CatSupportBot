from pydantic import BaseModel, field_validator
from datetime import date as date_type

class Transaction(BaseModel):
    """Базовая модель транзакции."""
    pet_name: str
    date: date_type
    amount: float
    comment: str | None = None
    author: str | None = None

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError('amount must be a positive number')
        return v

class Income(Transaction):
    """Модель для прихода (доната) с дополнительным полем 'bank'."""
    bank: str | None = None

class Expense(Transaction):
    """Модель для расхода с дополнительным полем 'procedure'."""
    procedure: str | None = None # НОВОЕ ПОЛЕ