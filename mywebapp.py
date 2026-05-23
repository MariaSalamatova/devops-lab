import argparse
import sys
import mysql.connector
from mysql.connector import Error
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

parser = argparse.ArgumentParser(description="MyWebApp")
parser.add_argument('--host', type=str, default='127.0.0.1', help='Interface to listen on')
parser.add_argument('--port', type=int, default=5000, help='Port to listen on')
parser.add_argument('--db_host', type=str, default='127.0.0.1', help='Database host')
parser.add_argument('--db_user', type=str, default='webapp_user', help='Database user')
parser.add_argument('--db_password', type=str, default='secure_password', help='Database password')
parser.add_argument('--db_name', type=str, default='mywebapp_db', help='Database name')
parser.add_argument('--socket_fd', type=int, default=None, help='Systemd Socket FD')
args, unknown = parser.parse_known_args()

def get_db_connection():
    return mysql.connector.connect(
        host=args.db_host,
        user=args.db_user,
        password=args.db_password,
        database=args.db_name
    )

def run_migrations():
    try:
        conn = mysql.connector.connect(
            host=args.db_host, user=args.db_user, password=args.db_password
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {args.db_name};")
        cursor.execute(f"USE {args.db_name};")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                status VARCHAR(50) DEFAULT 'todo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("Migrations completed successfully.")
    except Error as e:
        print(f"Migration error: {e}", file=sys.stderr)
        sys.exit(1)

@app.route('/health/alive', methods=['GET'])
def alive():
    return "OK", 200

@app.route('/health/ready', methods=['GET'])
def ready():
    try:
        conn = get_db_connection()
        if conn.is_connected():
            conn.close()
            return "OK", 200
    except Error as e:
        return f"Database unavailable: {str(e)}", 500

def respond(data, template_html):
    accept = request.headers.get('Accept', '')
    if 'application/json' in accept:
        return jsonify(data)
    else:
        return render_template_string(template_html, data=data)

@app.route('/', methods=['GET'])
def root():
    endpoints = ["/tasks (GET)", "/tasks (POST)", "/tasks/<id>/done (POST)"]
    html = "<h1>Available Business Logic Endpoints</h1><ul>{% for ep in data %}<li>{{ ep }}</li>{% endfor %}</ul>"
    return render_template_string(html, data=endpoints)

@app.route('/tasks', methods=['GET'])
def get_tasks():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, title, status, DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') as created_at FROM tasks")
        tasks = cursor.fetchall()
        cursor.close()
        conn.close()
    except Error:
        tasks = []

    html = """
    <h1>Tasks</h1>
    <table border="1">
        <tr><th>ID</th><th>Title</th><th>Status</th><th>Created At</th></tr>
        {% for t in data %}
        <tr><td>{{t.id}}</td><td>{{t.title}}</td><td>{{t.status}}</td><td>{{t.created_at}}</td></tr>
        {% endfor %}
    </table>
    """
    return respond(tasks, html)

@app.route('/tasks', methods=['POST'])
def create_task():
    title = None
    if request.is_json:
        title = request.json.get('title')
    else:
        title = request.form.get('title')

    if not title:
        return "Missing title", 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (title, status) VALUES (%s, 'todo')", (title,))
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()

    res = {"message": "Task created", "id": new_id}
    html = "<h1>Task Created</h1><p>ID: {{data.id}}</p>"
    return respond(res, html), 201

@app.route('/tasks/<int:task_id>/done', methods=['POST'])
def done_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status = 'done' WHERE id = %s", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()

    res = {"message": f"Task {task_id} marked as done"}
    html = "<h1>Task Updated</h1><p>{{data.message}}</p>"
    return respond(res, html)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--migrate':
        run_migrations()
        sys.exit(0)

    if args.socket_fd:
        from werkzeug.serving import run_simple
        import socket
        s = socket.fromfd(args.socket_fd, socket.AF_INET, socket.SOCK_STREAM)
        run_simple(args.host, args.port, app, fd=s.fileno())
    else:
        app.run(host=args.host, port=args.port)