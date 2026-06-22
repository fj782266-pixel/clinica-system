from app import db, app
import sqlite3

app.app_context().push()

# conecta no SQLite correto
sqlite_conn = sqlite3.connect("clinica.db")
sqlite_conn.row_factory = sqlite3.Row
cursor = sqlite_conn.cursor()

print("Conectado no SQLite")

# lista tabelas
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tabelas = cursor.fetchall()

print(tabelas)