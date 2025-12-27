from sqlalchemy import Table, Column, MetaData, BigInteger, DateTime, text, Text
from sqlalchemy.sql.schema import ForeignKey

metadata = MetaData()

eggs = Table(
    "eggs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("chicken_id", BigInteger, ForeignKey("chickens.id"), nullable=False),
    Column(
        "laid_at", DateTime(timezone=True), server_default=text("now()"), nullable=False
    ),
)

chickens = Table(
    "chickens",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("date_of_birth", DateTime(timezone=True), nullable=False),
    Column("date_of_death", DateTime(timezone=True), nullable=True),
    Column("tag_string", Text, nullable=False, unique=True),
)
