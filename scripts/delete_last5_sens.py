#!/usr/bin/env python3

from src.utils.config import get_config
from src.database.models import DatabaseManager


def main() -> None:
    config = get_config()
    db = DatabaseManager(config.database_path)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, sens_number, company_name, date_published, date_scraped
            FROM sens_announcements
            ORDER BY COALESCE(date_published, date_scraped) DESC
            LIMIT 5
            """
        )
        rows = cursor.fetchall()

        if not rows:
            print("No rows found")
            return

        ids = [row["id"] for row in rows]
        nums = [row["sens_number"] for row in rows]
        print("Deleting SENS:", nums)

        placeholders = ",".join(["?"] * len(ids))

        # Delete related notifications first
        cursor.execute(
            f"DELETE FROM notifications WHERE sens_id IN ({placeholders})",
            ids,
        )

        # Delete announcements
        cursor.execute(
            f"DELETE FROM sens_announcements WHERE id IN ({placeholders})",
            ids,
        )

        print("Deleted count:", len(ids))


if __name__ == "__main__":
    main()


