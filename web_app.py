# web_app.py
from flask import Flask, jsonify
from DBManager import DBManager

db=DBManager()
app = Flask(__name__)

# Use the shared connection
db_connection = init_connection()

@app.route("/")
def inspect_data():
    try:
        data=db.pull_table_data(db.gpt_query_table_name)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
