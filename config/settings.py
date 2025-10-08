# config/settings.py

from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""
    telegram_token: str
    
    # Ссылка на Google Таблицу - используем верхний регистр для консистентности
    GOOGLE_SHEETS_LINK: str = "https://docs.google.com/spreadsheets/d/1FBnDZdRy0KmBRFs5VmMBWCJmNhuXE--D0pPb6ghusFA/edit?gid=0#gid=0"
    
    # credentials.json лежит в корне проекта
    @property
    def google_credentials_path(self) -> str:
        return "credentials.json"
    
    class Config:
        env_file = ".env"
        case_sensitive = False  # Разрешаем любой регистр для переменных окружения

# Создаем глобальный экземпляр настроек
settings = Settings()