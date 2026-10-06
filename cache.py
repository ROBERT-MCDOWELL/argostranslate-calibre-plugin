import sqlite3
class TranslationCache:
    def __init__(self, path:str, src:str, dst:str):
        self.pair = f"{src}>{dst}"
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.execute('CREATE TABLE IF NOT EXISTS translations(pair TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL, PRIMARY KEY(pair, source))')
    def get_many(self, texts:list[str])->dict:
        found:dict = {}
        for start in range(0, len(texts), 500):
            chunk = texts[start:start + 500]
            marks = ','.join('?' * len(chunk))
            found.update(self.conn.execute(f"SELECT source, target FROM translations WHERE pair=? AND source IN ({marks})", [self.pair, *chunk]).fetchall())
        return found
    def put_many(self, items:dict)->None:
        self.conn.executemany('INSERT OR REPLACE INTO translations VALUES(?, ?, ?)', [(self.pair, source, target) for source, target in items.items()])
        self.conn.commit()
    def close(self)->None:
        self.conn.close()
