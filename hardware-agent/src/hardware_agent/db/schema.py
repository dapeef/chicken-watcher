from sqlalchemy import Table, Column, MetaData, BigInteger, DateTime, text

metadata = MetaData()

eggs = Table(
    "eggs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("hen_id", BigInteger, nullable=False, index=True),
    Column(
        "laid_at", DateTime(timezone=True), server_default=text("now()"), nullable=False
    ),
)
