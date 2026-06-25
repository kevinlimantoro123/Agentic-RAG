from sqlalchemy import text
from pipeline.precheck import engine
from sqlalchemy.exc import DatabaseError

def get_patient_list(pdf: str) -> list[str]:
    """
    Fetch distinct Patient names for a given PDF slug from the IRIS database.
    Returns a list of patient names (empty if slug is false or table doesn't exist).
    """
    # Query for distinct non-empty patient names
    sql = text(f'''
        SELECT DISTINCT Patient
          FROM Embedding.Clinical
         WHERE PDF = :pdf
          AND Patient IS NOT NULL 
          AND Patient != ""
         ORDER BY Patient
    ''')
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, {"pdf": pdf}).fetchall()
    except DatabaseError:
        # Table doesn't exist or other DB error
        return []
    return [row[0] for row in rows]

def get_pdf_list() -> list[str]:
    """
    Fetch distinct Patient names for a given PDF slug from the IRIS database.
    Returns a list of patient names (empty if slug is false or table doesn't exist).
    """
    # Query for distinct non-empty patient names
    sql = text(f'''
        SELECT DISTINCT PDF
          FROM Embedding.Clinical
         WHERE PDF IS NOT NULL AND PDF != ""
         ORDER BY PDF
    ''')
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
    except DatabaseError:
        # Table doesn't exist or other DB error
        return []
    return [row[0] for row in rows]