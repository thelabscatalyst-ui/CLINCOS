from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"  # Twilio sandbox default
    TWILIO_SMS_FROM: str = ""  # optional: your Twilio SMS phone number e.g. +918XXXXXXXXX

    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""

    ADMIN_EMAIL: str = ""  # platform owner email — set in .env

    class Config:
        env_file = ".env"


settings = Settings()
