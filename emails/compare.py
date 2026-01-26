import sqlite3
from transactionHandler import DB_PATH

def compare_test_vs_prod():
    exists = []
    missing = []

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                t.id,
                t.purchaseDate,
                t.amount,
                t.merchant,
                t.account_id,
                p.id IS NOT NULL AS exists_in_prod
            FROM transactions_test t
            LEFT JOIN transactions p
                ON REPLACE(REPLACE(t.id, '_0', ''), '_1', '')
             = REPLACE(REPLACE(p.id, '_0', ''), '_1', '')
            ORDER BY t.purchaseDate
        """)

        for row in cur.fetchall():
            tx = {
                "id": row[0],
                "purchaseDate": row[1],
                "amount": row[2],
                "merchant": row[3],
                "account_id": row[4],
            }

            if row[5]:
                exists.append(tx)
            else:
                missing.append(tx)

    return exists, missing


if __name__ == "__main__":
    exists, missing = compare_test_vs_prod()

    print("=== ALREADY IN transactions ===")
    for tx in exists:
        print(tx)

    print("\n=== NOT YET IN transactions ===")
    for tx in missing:
        print(tx)
