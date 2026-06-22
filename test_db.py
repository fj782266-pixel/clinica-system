from sqlalchemy import create_engine

engine = create_engine(
    "postgresql+psycopg://postgres:felipegk%4018@localhost:5432/clinica"
)
with engine.connect() as conn:
    print("CONECTOU COM SUCESSO")