"""Optional, incrementally maintained trigram search indexes for local text."""

import sqlite3


def init_search_index(conn):
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS paper_search_fts USING "
                     "fts5(uid UNINDEXED,title,abstract,tokenize='trigram')")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS passage_search_fts USING "
                     "fts5(id UNINDEXED,document_id UNINDEXED,heading,text,tokenize='trigram')")
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS paper_search_insert AFTER INSERT ON papers BEGIN
              INSERT INTO paper_search_fts(rowid,uid,title,abstract)
              VALUES(new.rowid,new.uid,new.title,new.abstract);
            END;
            CREATE TRIGGER IF NOT EXISTS paper_search_update AFTER UPDATE ON papers BEGIN
              DELETE FROM paper_search_fts WHERE rowid=old.rowid;
              INSERT INTO paper_search_fts(rowid,uid,title,abstract)
              VALUES(new.rowid,new.uid,new.title,new.abstract);
            END;
            CREATE TRIGGER IF NOT EXISTS paper_search_delete AFTER DELETE ON papers BEGIN
              DELETE FROM paper_search_fts WHERE rowid=old.rowid;
            END;
            CREATE TRIGGER IF NOT EXISTS passage_search_insert AFTER INSERT ON passages BEGIN
              INSERT INTO passage_search_fts(rowid,id,document_id,heading,text)
              VALUES(new.rowid,new.id,new.document_id,new.heading,new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS passage_search_update AFTER UPDATE ON passages BEGIN
              DELETE FROM passage_search_fts WHERE rowid=old.rowid;
              INSERT INTO passage_search_fts(rowid,id,document_id,heading,text)
              VALUES(new.rowid,new.id,new.document_id,new.heading,new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS passage_search_delete AFTER DELETE ON passages BEGIN
              DELETE FROM passage_search_fts WHERE rowid=old.rowid;
            END;
        """)
        # This also upgrades databases created before the indexes existed.
        conn.execute("INSERT INTO paper_search_fts(rowid,uid,title,abstract) "
                     "SELECT rowid,uid,title,abstract FROM papers WHERE rowid NOT IN "
                     "(SELECT rowid FROM paper_search_fts)")
        conn.execute("INSERT INTO passage_search_fts(rowid,id,document_id,heading,text) "
                     "SELECT rowid,id,document_id,heading,text FROM passages WHERE rowid NOT IN "
                     "(SELECT rowid FROM passage_search_fts)")
    except sqlite3.OperationalError:
        # Older SQLite builds still use the exact same scan-based API behavior.
        return False
    return True


def available(conn):
    return all(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            (name,)).fetchone() for name in
               ("paper_search_fts", "passage_search_fts"))
