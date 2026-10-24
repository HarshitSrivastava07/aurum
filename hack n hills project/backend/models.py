"""Validated, bounded public research configuration."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Symbol = Literal["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]


class CostSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schedule_id: str = Field(min_length=1,max_length=100)
    effective_from: date
    effective_to: date | None = None
    brokerage_per_lot: float = Field(0,ge=0,le=100000)
    exchange_bps: float = Field(0,ge=0,le=1000)
    regulatory_bps: float = Field(0,ge=0,le=1000)
    buy_tax_bps: float = Field(0,ge=0,le=1000)
    sell_tax_bps: float = Field(0,ge=0,le=1000)
    gst_fraction: float = Field(0,ge=0,le=1)
    extra_per_lot: float = Field(0,ge=0,le=100000)


class ResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    pair: tuple[Symbol, Symbol] = ("GOLDM", "GOLDTEN")
    expiry_a: date | None = None
    expiry_b: date | None = None
    start: date | None = None
    end: date | None = None
    cutoff: date | None = None
    window: int = Field(20, ge=5, le=252)
    z_threshold: float = Field(2.0, ge=0.5, le=10)
    capital: float = Field(10_000_000, gt=0, le=1e12)
    max_lots: int = Field(100, ge=1, le=1000)
    min_volume: int = Field(10, ge=1, le=100000000)
    min_oi: int = Field(10, ge=1, le=100000000)
    holding_days: int = Field(5, ge=1, le=60)
    execution_delay: int = Field(1, ge=1, le=20)
    exit_delay: int = Field(0, ge=0, le=20)
    cost_bps: float = Field(5, ge=0, le=1000)
    slippage_bps: float = Field(2, ge=0, le=1000)
    seed: int = Field(42, ge=0, le=2**32-1)
    simulations: int = Field(500, ge=50, le=10000)
    volatility_stress: float = Field(1, ge=0.1, le=5)
    mode: Literal["real", "synthetic"] = "real"
    baseline: Literal["A", "B", "C"] = "C"
    cost_schedule: list[CostSchedule] = Field(default_factory=list,max_length=50)

    @model_validator(mode="after")
    def check_dates(self):
        if self.pair[0] == self.pair[1]:
            raise ValueError("Choose two distinct products; calendar spreads use the curve laboratory.")
        if self.start and self.end and self.start > self.end:
            raise ValueError("Start must precede end.")
        if self.start and self.cutoff and self.start > self.cutoff:
            raise ValueError("Start must not follow the information cutoff.")
        for value in (self.start, self.end, self.cutoff):
            if value and value > date.today():
                raise ValueError("Research dates cannot be in the future.")
        ordered=sorted(self.cost_schedule,key=lambda s:s.effective_from)
        for i,schedule in enumerate(ordered):
            if schedule.effective_to and schedule.effective_to<schedule.effective_from:
                raise ValueError("Cost schedule end precedes its start")
            if i and (ordered[i-1].effective_to is None or ordered[i-1].effective_to>=schedule.effective_from):
                raise ValueError("Cost schedule dates overlap")
        return self

    def as_dict(self):
        return self.model_dump(mode="json")
