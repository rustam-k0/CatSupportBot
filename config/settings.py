from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""
    telegram_token: str
    
    # credentials.json лежит в корне проекта, не нужно указывать в .env
    @property
    def google_credentials_path(self) -> str:
        return "credentials.json"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Создаем глобальный экземпляр настроек
settings = Settings()