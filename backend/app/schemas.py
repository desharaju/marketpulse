from pydantic import BaseModel, EmailStr, Field, field_validator


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z][A-Za-z0-9.\-]*$")

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()


class AlertCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z][A-Za-z0-9.\-]*$")
    metric: str = Field(pattern=r"^(relativeVolume|changePercent|price)$")
    threshold: float
    direction: str = Field(default="above", pattern=r"^(above|below)$")

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()


class ReportRequest(BaseModel):
    recipient: EmailStr | None = None
    send: bool = False


class TestEmailRequest(BaseModel):
    recipient: EmailStr


class ReportConfigUpdate(BaseModel):
    recipient: EmailStr | None = None
    additional_recipients: list[EmailStr] = Field(default_factory=list, max_length=10)
    report_time: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    min_relative_volume: float = Field(default=2, ge=1, le=100)
    min_change_percent: float = Field(default=0, ge=0, le=1000)
    min_price: float = Field(default=0, ge=0)
    min_dollar_volume: float = Field(default=0, ge=0)
    max_tickers_per_section: int = Field(default=10, ge=1, le=100)
    format: str = Field(default="html", pattern="^(html|text)$")