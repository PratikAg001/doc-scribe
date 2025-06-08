import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.errors import ServerSelectionTimeoutError
from config.settings import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Singleton database connection manager with connection pooling"""
    
    _instance: Optional['DatabaseManager'] = None
    _client: Optional[AsyncIOMotorClient] = None
    _database: Optional[AsyncIOMotorDatabase] = None
    
    def __new__(cls) -> 'DatabaseManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect(self) -> None:
        """Initialize database connection with connection pooling"""
        if self._client is None:
            try:
                self._client = AsyncIOMotorClient(
                    settings.mongo_url,
                    maxPoolSize=settings.db_connection_pool_size,
                    minPoolSize=1,
                    maxIdleTimeMS=30000,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=10000
                )
                
                # Test connection
                await self._client.admin.command('ping')
                self._database = self._client[settings.db_name]
                
                # Create indexes for better performance
                await self._create_indexes()
                
                logger.info(f"Connected to MongoDB: {settings.db_name}")
                
            except ServerSelectionTimeoutError as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise
            except Exception as e:
                logger.error(f"Database connection error: {e}")
                raise
    
    async def disconnect(self) -> None:
        """Close database connection"""
        if self._client:
            self._client.close()
            self._client = None
            self._database = None
            logger.info("Disconnected from MongoDB")
    
    async def _create_indexes(self) -> None:
        """Create database indexes for performance optimization"""
        if self._database is not None:
            try:
                # Sessions collection indexes
                await self._database.recordings.create_index("session_id", unique=True)
                await self._database.recordings.create_index("created_at")
                await self._database.recordings.create_index("status")
                
                # Feedback collection indexes
                await self._database.feedback.create_index("session_id")
                await self._database.feedback.create_index("submitted_at")
                
                # Analytics collection indexes
                await self._database.analytics.create_index("session_id")
                await self._database.analytics.create_index("processed_at")
                
                logger.info("Database indexes created successfully")
                
            except Exception as e:
                logger.warning(f"Failed to create indexes: {e}")
    
    @property
    def database(self) -> AsyncIOMotorDatabase:
        """Get database instance"""
        if self._database is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._database
    
    @property
    def recordings(self) -> AsyncIOMotorCollection:
        """Get recordings collection"""
        return self.database.recordings
    
    @property
    def feedback(self) -> AsyncIOMotorCollection:
        """Get feedback collection"""
        return self.database.feedback
    
    @property
    def analytics(self) -> AsyncIOMotorCollection:
        """Get analytics collection"""
        return self.database.analytics

# Global database manager instance
db_manager = DatabaseManager()

async def get_database() -> DatabaseManager:
    """Get database manager instance"""
    if db_manager._database is None:
        await db_manager.connect()
    return db_manager
