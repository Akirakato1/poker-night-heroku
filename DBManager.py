from rethinkdb import RethinkDB
import threading
import time
import os

class DBManager:
    def __init__(self):
        self.r = RethinkDB()
        self.conn = self.connect_rethinkdb()

    def connect_rethinkdb(self):
        try:
            conn = self.r.connect(
                host=os.getenv('RETHINKDB_HOST'),
                port=int(os.getenv('RETHINKDB_PORT')),
                db=os.getenv('RETHINKDB_NAME'),
                user=os.getenv('RETHINKDB_USERNAME'),
                password=os.getenv('RETHINKDB_PASSWORD')
            )
            return conn
        except Exception as e:
            print("Error connecting to RethinkDB:", e)
            return None

    def keep_alive_rethinkdb(self):
        def maintain_rethinkdb_connection():
            while True:
                try:
                    if self.conn is None or not self.conn.is_open():
                        print("Reconnecting to RethinkDB...")
                        self.conn = self.connect_rethinkdb()
                    else:
                        # Ping the server to keep the connection active
                        self.r.now().run(self.conn)
                except Exception as e:
                    print("Error maintaining connection:", e)
                time.sleep(60)  # Wait for 1 minute before checking again
        threading.Thread(target=self.maintain_rethinkdb_connection, daemon=True).start()

    def create_table(self, table_name):
        try:
            if table_name not in self.r.db(os.getenv('RETHINKDB_NAME')).table_list().run(self.conn):
                self.r.db(os.getenv('RETHINKDB_NAME')).table_create(table_name).run(self.conn)
                print(f"Table '{table_name}' created.")
            else:
                print(f"Table '{table_name}' already exists.")
        except Exception as e:
            print("Error creating table:", e)

    def push_document(self, table_name, document):
        try:
            self.r.table(table_name).insert(document).run(self.conn)
            print(f"Document inserted into '{table_name}':", document)
        except Exception as e:
            print("Error inserting document:", e)

    def pull_table_data(self, table_name):
        try:
            data = list(self.r.table(table_name).run(self.conn))
            print(f"Data pulled from '{table_name}':", data)
            return data
        except Exception as e:
            print("Error pulling data:", e)
            return []
