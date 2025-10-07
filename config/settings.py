from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Указываем, что переменные будут браться из файла .env
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Обязательная переменная - токен для Telegram бота
    telegram_token: str

# Создаем экземпляр настроек, который будем использовать в проекте
settings = Settings()