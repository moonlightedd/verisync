
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "verisync.db")


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    connection = get_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS kyc_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verification_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            masked_aadhaar TEXT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            system_status TEXT,
            failure_reason TEXT,
            video_path TEXT,
            audio_path TEXT,
            cross_modal_score REAL,
            face_status TEXT,
            audio_status TEXT
        )
        """
    )

    connection.commit()
    connection.close()


def _clean_identity_value(value, fallback="Not Available"):
    """Normalize identity fields before saving them."""
    if value is None:
        return fallback

    cleaned = str(value).strip()

    if not cleaned:
        return fallback

    return cleaned


def _clean_phone_number(value):
    """Normalize phone number without altering the user's actual digits."""
    cleaned = _clean_identity_value(value, "Not Available")

    if cleaned == "Not Available":
        return cleaned

    return cleaned


def create_kyc_record(
    verification_id,
    full_name,
    phone_number,
    masked_aadhaar,
    status,
    system_status,
    failure_reason,
    video_path,
    audio_path,
    cross_modal_score,
    face_status,
    audio_status,
):
    connection = get_connection()

    # Normalize identity fields so blank values are never stored.
    # The actual customer name/phone must still be supplied by the
    # E-KYC page; the database cannot invent missing identity data.
    full_name = _clean_identity_value(full_name, "Unknown User")
    phone_number = _clean_phone_number(phone_number)
    masked_aadhaar = _clean_identity_value(
        masked_aadhaar,
        "Not Available",
    )

    connection.execute(
        """
        INSERT OR REPLACE INTO kyc_records (
            verification_id,
            full_name,
            phone_number,
            masked_aadhaar,
            timestamp,
            status,
            system_status,
            failure_reason,
            video_path,
            audio_path,
            cross_modal_score,
            face_status,
            audio_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _clean_identity_value(
                verification_id,
                "UNKNOWN-VERIFICATION",
            ),
            full_name,
            phone_number,
            masked_aadhaar,
            datetime.now().isoformat(timespec="seconds"),
            _clean_identity_value(status, "REVIEW"),
            _clean_identity_value(system_status, "Unknown"),
            _clean_identity_value(
                failure_reason,
                "",
            ),
            _clean_identity_value(video_path, ""),
            _clean_identity_value(audio_path, ""),
            float(cross_modal_score or 0),
            _clean_identity_value(face_status, "N/A"),
            _clean_identity_value(audio_status, "N/A"),
        ),
    )

    connection.commit()
    connection.close()


def update_kyc_identity(
    verification_id,
    full_name,
    phone_number,
    masked_aadhaar=None,
):
    """
    Update customer identity information for an existing verification.

    This is useful when identity details are collected in an earlier
    E-KYC step and the verification record is created afterward.
    """
    connection = get_connection()

    full_name = _clean_identity_value(full_name, "Unknown User")
    phone_number = _clean_phone_number(phone_number)

    if masked_aadhaar is None:
        connection.execute(
            """
            UPDATE kyc_records
            SET full_name = ?,
                phone_number = ?
            WHERE verification_id = ?
            """,
            (
                full_name,
                phone_number,
                verification_id,
            ),
        )
    else:
        connection.execute(
            """
            UPDATE kyc_records
            SET full_name = ?,
                phone_number = ?,
                masked_aadhaar = ?
            WHERE verification_id = ?
            """,
            (
                full_name,
                phone_number,
                _clean_identity_value(
                    masked_aadhaar,
                    "Not Available",
                ),
                verification_id,
            ),
        )

    connection.commit()
    changed = connection.total_changes
    connection.close()

    return changed > 0


def get_recent_kycs(limit=20):
    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *
        FROM kyc_records
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    connection.close()
    return rows


def search_kycs(query):
    connection = get_connection()

    pattern = f"%{query}%"

    rows = connection.execute(
        """
        SELECT *
        FROM kyc_records
        WHERE full_name LIKE ?
           OR phone_number LIKE ?
           OR verification_id LIKE ?
        ORDER BY id DESC
        """,
        (pattern, pattern, pattern),
    ).fetchall()

    connection.close()
    return rows


def get_kyc_by_id(verification_id):
    connection = get_connection()

    row = connection.execute(
        """
        SELECT *
        FROM kyc_records
        WHERE verification_id = ?
        """,
        (verification_id,),
    ).fetchone()

    connection.close()
    return row


def delete_kyc_by_id(verification_id):
    """
    Delete one KYC record from the database and return
    the stored evidence paths so the caller can remove
    the corresponding evidence folder/files.
    """
    connection = get_connection()

    row = connection.execute(
        """
        SELECT video_path, audio_path
        FROM kyc_records
        WHERE verification_id = ?
        """,
        (verification_id,),
    ).fetchone()

    if row is None:
        connection.close()
        return None

    connection.execute(
        """
        DELETE FROM kyc_records
        WHERE verification_id = ?
        """,
        (verification_id,),
    )

    connection.commit()
    connection.close()

    return {
        "video_path": row["video_path"],
        "audio_path": row["audio_path"],
    }


def delete_all_kycs():
    """
    Delete all database records.
    Returns the stored video/audio paths first so the caller
    can remove the associated evidence folders.
    """
    connection = get_connection()

    rows = connection.execute(
        """
        SELECT verification_id, video_path, audio_path
        FROM kyc_records
        """
    ).fetchall()

    connection.execute("DELETE FROM kyc_records")
    connection.commit()
    connection.close()

    return [
        {
            "verification_id": row["verification_id"],
            "video_path": row["video_path"],
            "audio_path": row["audio_path"],
        }
        for row in rows
    ]
