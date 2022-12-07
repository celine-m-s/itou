import logging

import psycopg2
from django.conf import settings
from psycopg2.extras import LoggingConnection, LoggingCursor


logger = logging.getLogger("django.db.backends")


class MetabaseDatabaseCursor:
    def __init__(self):
        self.cursor = None
        self.connection = None

    def __enter__(self):
        self.connection = psycopg2.connect(
            host=settings.METABASE_HOST,
            port=settings.METABASE_PORT,
            dbname=settings.METABASE_DATABASE,
            user=settings.METABASE_USER,
            password=settings.METABASE_PASSWORD,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=5,
            keepalives_count=5,
            connection_factory=LoggingConnection,
        )
        self.connection.initialize(logger)
        self.cursor = self.connection.cursor(cursor_factory=LoggingCursor if settings.SQL_DEBUG else None)
        return self.cursor, self.connection

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
