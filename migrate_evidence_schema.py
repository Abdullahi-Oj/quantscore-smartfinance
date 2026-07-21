import sqlite3
conn = sqlite3.connect('smartfinance.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evidence'")
if cur.fetchone():
    cur.execute('ALTER TABLE evidence RENAME TO evidence_old')
    cur.execute('''
    CREATE TABLE evidence (
        id INTEGER NOT NULL,
        merchant_id INTEGER NOT NULL,
        evidence_type VARCHAR(13) NOT NULL,
        file_path VARCHAR(500),
        file_content TEXT,
        status VARCHAR(9) NOT NULL,
        extracted_data JSON,
        confidence_score FLOAT,
        is_validated BOOLEAN NOT NULL,
        validation_notes TEXT,
        uploaded_at DATETIME NOT NULL,
        processed_at DATETIME,
        PRIMARY KEY (id),
        FOREIGN KEY(merchant_id) REFERENCES merchants (id)
    )
    ''')
    cur.execute('''
    INSERT INTO evidence (
        id, merchant_id, evidence_type, file_path, file_content, status,
        extracted_data, confidence_score, is_validated, validation_notes,
        uploaded_at, processed_at
    )
    SELECT
        id, merchant_id, evidence_type, file_path, CAST(file_content AS TEXT), status,
        extracted_data, confidence_score, is_validated, validation_notes,
        uploaded_at, processed_at
    FROM evidence_old
    ''')
    cur.execute('DROP TABLE evidence_old')
    conn.commit()
print('evidence_table_rebuilt')
conn.close()
