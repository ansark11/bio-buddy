from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    ollama_base_url: str = "http://localhost:11434"
    groq_api_key: str = ""
    cohere_api_key: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:8000/api/ingest/nutrition/gmail-callback"
    gmail_token_file: str = ".gmail_token.json"
    lose_it_sender_email: str = ""
    scheduled_user_id: str = ""
    cors_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
