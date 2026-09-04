"""
database.py
------------
SQLite database layer for the AI Invoice Analyzer.

Tables:
  invoices   -> one row per uploaded invoice (header data)
  line_items -> one row per product/line inside an invoice (many-to-one)

Uses plain sqlite3 (no ORM) to keep the MVP lightweight and dependency-free.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "invoices.db"


def init_db(db_path: str = DB_PATH):
    """Create tables if they don't already exist."""
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number  TEXT,
                invoice_date    TEXT,
                vendor          TEXT,
                total_amount    REAL,
                source_file     TEXT,
                raw_text        TEXT,
                created_at      TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS line_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id   INTEGER NOT NULL,
                product      TEXT,
                quantity     REAL,
                unit_price   REAL,
                line_total   REAL,
                FOREIGN KEY (invoice_id) REFERENCES invoices (id)
            )
        """)
        conn.commit()


@contextmanager
def get_connection(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def save_invoice(data: dict, db_path: str = DB_PATH) -> int:
    """
    Persist a parsed invoice (and its line items) to the database.

    `data` is expected to look like the dict produced by
    ocr_extractor.extract_invoice_data(), i.e.:
        {
            "invoice_number": str,
            "invoice_date": str,
            "vendor": str,
            "total_amount": float,
            "source_file": str,
            "raw_text": str,
            "line_items": [
                {"product": str, "quantity": float,
                 "unit_price": float, "line_total": float},
                ...
            ]
        }
    Returns the new invoice id.
    """
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO invoices
               (invoice_number, invoice_date, vendor, total_amount,
                source_file, raw_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("invoice_number"),
                data.get("invoice_date"),
                data.get("vendor"),
                data.get("total_amount"),
                data.get("source_file"),
                data.get("raw_text"),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        invoice_id = cur.lastrowid

        for item in data.get("line_items", []):
            conn.execute(
                """INSERT INTO line_items
                   (invoice_id, product, quantity, unit_price, line_total)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    invoice_id,
                    item.get("product"),
                    item.get("quantity"),
                    item.get("unit_price"),
                    item.get("line_total"),
                ),
            )
        conn.commit()
        return invoice_id


def get_all_invoices(db_path: str = DB_PATH):
    """Return all invoices as a list of sqlite3.Row objects."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM invoices ORDER BY created_at DESC"
        ).fetchall()


def get_all_line_items(db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        return conn.execute("SELECT * FROM line_items").fetchall()


def get_invoice_with_items(invoice_id: int, db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        invoice = conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        items = conn.execute(
            "SELECT * FROM line_items WHERE invoice_id = ?", (invoice_id,)
        ).fetchall()
        return invoice, items


def delete_invoice(invoice_id: int, db_path: str = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM line_items WHERE invoice_id = ?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        conn.commit()


def reset_db(db_path: str = DB_PATH):
    """Danger: wipes all data. Used by the 'Reset demo data' button."""
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM line_items")
        conn.execute("DELETE FROM invoices")
        conn.commit()
