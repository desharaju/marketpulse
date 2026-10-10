from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./marketpulse.db"
    finnhub_api_key: str = ""
    admin_api_key: str = ""
    market_symbols: str = "AAPL,MSFT,NVDA,AMZN,TSLA,META,AMD,PLTR,SMCI,COIN"
    refresh_seconds: int = 60
    cors_origins: str = "http://localhost:3000"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "MarketPulse <reports@example.com>"
    report_recipient: str = ""
    report_time: str = "08:00"
    dashboard_url: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def symbols(self) -> list[str]:
        return list(dict.fromkeys(symbol.strip().upper() for symbol in self.market_symbols.split(",") if symbol.strip()))

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()