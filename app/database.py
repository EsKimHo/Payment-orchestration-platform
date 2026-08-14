import os
from sqlalchemy import create_engine # to create a connection to database
from sqlalchemy.orm import sessionmaker, declarative_base 

DATABASE_URL=os.getenv("DATABASE_URL", "postgresql+psycopg2://postgre535:123456789@localhost:5432/payments")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()