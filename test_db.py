
import os
import oracledb
from dotenv import load_dotenv

load_dotenv()

wallet_dir = os.environ["DB_WALLET_DIR"]

with oracledb.connect(
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    dsn=os.environ["DB_DSN"],
    config_dir=wallet_dir,
    wallet_location=wallet_dir,
    wallet_password=os.environ["DB_WALLET_PASSWORD"],
) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM waste_events")
        count = cursor.fetchone()[0]
        print(f"Connected to OCI! Waste events: {count}")
