from flask import Flask, request, jsonify, render_template
import sqlite3
import os

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'tasks.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            priority    TEXT    DEFAULT 'medium',
            category    TEXT    DEFAULT 'general',
            due_date    TEXT    DEFAULT '',
            alarm_time  TEXT    DEFAULT '',
            completed   INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        )
    ''')
    conn.commit()
    conn.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM tasks ORDER BY completed ASC, created_at DESC'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tasks', methods=['POST'])
def create_task():
    d = request.json or {}
    if not d.get('title', '').strip():
        return jsonify({'error': 'Title is required'}), 400
    conn = get_db()
    cur = conn.execute(
        '''INSERT INTO tasks (title, description, priority, category, due_date, alarm_time)
           VALUES (?,?,?,?,?,?)''',
        (d['title'].strip(), d.get('description', ''), d.get('priority', 'medium'),
         d.get('category', 'general'), d.get('due_date', ''), d.get('alarm_time', ''))
    )
    task_id = cur.lastrowid
    conn.commit()
    task = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    conn.close()
    return jsonify(dict(task)), 201


@app.route('/api/tasks/<int:tid>', methods=['PUT'])
def update_task(tid):
    d = request.json or {}
    fields = ['title', 'description', 'priority', 'category', 'due_date', 'alarm_time', 'completed']
    allowed = {f: d[f] for f in fields if f in d}
    if not allowed:
        return jsonify({'error': 'Nothing to update'}), 400
    sets = ', '.join(f'{k}=?' for k in allowed)
    vals = list(allowed.values()) + [tid]
    conn = get_db()
    conn.execute(f'UPDATE tasks SET {sets} WHERE id=?', vals)
    conn.commit()
    task = conn.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
    conn.close()
    if task is None:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(task))


@app.route('/api/tasks/<int:tid>', methods=['DELETE'])
def delete_task(tid):
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id=?', (tid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    print('\n  TaskPulse is running!')
    print('  Open http://localhost:5000 in your browser')
    print('  Press Ctrl+C to stop\n')
    app.run(debug=False, port=5000)
