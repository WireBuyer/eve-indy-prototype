import sqlite3

DB_PATH = "eve.db"


def lookup(type_id, conn):
    cur = conn.execute("SELECT typeName FROM inv_types WHERE typeID = ?", (type_id,))
    row = cur.fetchone()
    return row[0] if row else "not found"


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        while True:
            s = input("Enter type id (or blank to quit): ").strip()
            if not s:
                break
            try:
                tid = int(s)
            except ValueError:
                print("not found")
                continue
            print(lookup(tid, conn))
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
