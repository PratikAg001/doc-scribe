import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Database
    mongo_url: str = "mongodb://localhost:27017"
    db_name: str = "test_database"
    
    # External APIs
    deepgram_api_key: str
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_deployment_name: str
    azure_openai_api_version: str = "2024-02-15-preview"
    
    # Application
    debug: bool = False
    log_level: str = "INFO"
    
    # Audio Processing
    audio_chunk_size: int = 4096
    audio_sample_rate: int = 16000
    transcription_interval_chunks: int = 32  # Process every 2 seconds
    
    # Performance
    max_concurrent_sessions: int = 50
    db_connection_pool_size: int = 10
    audio_buffer_cleanup_interval: int = 300  # 5 minutes
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()
