from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sqlite3, os, bcrypt, json, smtplib, threading, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, date

# ── Google library imports (optional) ─────────────────────────
try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_LIBS = True
except ImportError:
    GOOGLE_LIBS = False

# ── Config ─────────────────────────────────────────────────────
try:
    import config as _cfg
    SECRET_KEY           = _cfg.SECRET_KEY
    GOOGLE_CLIENT_ID     = getattr(_cfg, 'GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = getattr(_cfg, 'GOOGLE_CLIENT_SECRET', '')
    GOOGLE_REDIRECT_URI  = getattr(_cfg, 'GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/google/callback')
    GMAIL_SENDER         = getattr(_cfg, 'GMAIL_SENDER', '')
    GMAIL_APP_PASSWORD   = getattr(_cfg, 'GMAIL_APP_PASSWORD', '')
except ImportError:
    SECRET_KEY = 'insecure-default-please-set-config-py'
    GOOGLE_CLIENT_ID = GOOGLE_CLIENT_SECRET = GMAIL_SENDER = GMAIL_APP_PASSWORD = ''
    GOOGLE_REDIRECT_URI = 'http://localhost:5000/auth/google/callback'

GOOGLE_AVAILABLE = GOOGLE_LIBS and bool(GOOGLE_CLIENT_ID)
GOOGLE_SCOPES    = ['https://www.googleapis.com/auth/calendar']

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # allow HTTP for local dev

# ── App setup ──────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY
DB_PATH = os.path.join(os.path.dirname(__file__), 'tasks.db')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

# ── User model ─────────────────────────────────────────────────
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id       = id
        self.username = username
        self.email    = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row  = conn.execute('SELECT id, username, email FROM users WHERE id=?', (int(user_id),)).fetchone()
    conn.close()
    return User(row['id'], row['username'], row['email']) if row else None

# ── Database ───────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            email         TEXT    DEFAULT ''
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS google_tokens (
            user_id      INTEGER PRIMARY KEY,
            token_json   TEXT    NOT NULL,
            google_email TEXT    DEFAULT ''
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER DEFAULT 1,
            title         TEXT    NOT NULL,
            description   TEXT    DEFAULT '',
            priority      TEXT    DEFAULT 'medium',
            category      TEXT    DEFAULT 'general',
            due_date      TEXT    DEFAULT '',
            alarm_time    TEXT    DEFAULT '',
            completed     INTEGER DEFAULT 0,
            gcal_event_id TEXT    DEFAULT '',
            reminder_sent INTEGER DEFAULT 0,
            created_at    TEXT    DEFAULT (datetime('now','localtime'))
        )
    ''')
    conn.commit()

    # Migrate existing tasks table if columns are missing
    for alter, fix in [
        ('ALTER TABLE tasks ADD COLUMN user_id INTEGER DEFAULT 1',
         'UPDATE tasks SET user_id=1 WHERE user_id IS NULL'),
        ('ALTER TABLE tasks ADD COLUMN gcal_event_id TEXT DEFAULT ""', None),
        ('ALTER TABLE tasks ADD COLUMN reminder_sent INTEGER DEFAULT 0', None),
    ]:
        try:
            conn.execute(alter)
            conn.commit()
            if fix:
                conn.execute(fix)
                conn.commit()
        except Exception:
            pass

    conn.close()

# ═══════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login_post():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    if not username or not password:
        return render_template('login.html', error='Username and password required')
    conn = get_db()
    row  = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    if not row or not bcrypt.checkpw(password.encode(), row['password_hash'].encode()):
        return render_template('login.html', error='Invalid username or password')
    login_user(User(row['id'], row['username'], row['email']), remember=True)
    return redirect(url_for('index'))

@app.route('/register', methods=['GET'])
def register_page():
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register_post():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm  = request.form.get('confirm', '')
    email    = request.form.get('email', '').strip()

    if not username or not password:
        return render_template('register.html', error='Username and password required')
    if len(username) < 3:
        return render_template('register.html', error='Username must be at least 3 characters')
    if len(password) < 6:
        return render_template('register.html', error='Password must be at least 6 characters')
    if password != confirm:
        return render_template('register.html', error='Passwords do not match')

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        conn = get_db()
        conn.execute('INSERT INTO users (username, password_hash, email) VALUES (?,?,?)',
                     (username, pw_hash, email))
        conn.commit()
        row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        conn.close()
        login_user(User(row['id'], row['username'], row['email']), remember=True)
        return redirect(url_for('index'))
    except sqlite3.IntegrityError:
        return render_template('register.html', error='Username already taken')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_page'))

# ═══════════════════════════════════════════════════════════════
# MAIN PAGE
# ═══════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    conn     = get_db()
    gcal_row = conn.execute('SELECT google_email FROM google_tokens WHERE user_id=?',
                             (current_user.id,)).fetchone()
    conn.close()
    return render_template('index.html',
                           username=current_user.username,
                           gcal_connected=gcal_row is not None,
                           gcal_email=gcal_row['google_email'] if gcal_row else '',
                           google_available=GOOGLE_AVAILABLE)

# ═══════════════════════════════════════════════════════════════
# TASK API
# ═══════════════════════════════════════════════════════════════

@app.route('/api/tasks', methods=['GET'])
@login_required
def get_tasks():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM tasks WHERE user_id=? ORDER BY completed ASC, created_at DESC',
        (current_user.id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/tasks', methods=['POST'])
@login_required
def create_task():
    d = request.json or {}
    if not d.get('title', '').strip():
        return jsonify({'error': 'Title is required'}), 400
    conn = get_db()
    cur  = conn.execute(
        'INSERT INTO tasks (user_id, title, description, priority, category, due_date, alarm_time) '
        'VALUES (?,?,?,?,?,?,?)',
        (current_user.id, d['title'].strip(), d.get('description', ''),
         d.get('priority', 'medium'), d.get('category', 'general'),
         d.get('due_date', ''), d.get('alarm_time', ''))
    )
    task_id = cur.lastrowid
    conn.commit()
    task = dict(conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone())
    conn.close()

    if task.get('due_date'):
        try:
            event_id = _create_cal_event(current_user.id, task)
            if event_id:
                conn2 = get_db()
                conn2.execute('UPDATE tasks SET gcal_event_id=? WHERE id=?', (event_id, task_id))
                conn2.commit()
                conn2.close()
                task['gcal_event_id'] = event_id
        except Exception as e:
            print(f'Calendar create error: {e}')

    return jsonify(task), 201

@app.route('/api/tasks/<int:tid>', methods=['PUT'])
@login_required
def update_task(tid):
    d       = request.json or {}
    fields  = ['title', 'description', 'priority', 'category', 'due_date', 'alarm_time', 'completed']
    allowed = {f: d[f] for f in fields if f in d}
    if not allowed:
        return jsonify({'error': 'Nothing to update'}), 400

    conn     = get_db()
    old_task = conn.execute('SELECT * FROM tasks WHERE id=? AND user_id=?',
                             (tid, current_user.id)).fetchone()
    if old_task is None:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    sets = ', '.join(f'{k}=?' for k in allowed)
    vals = list(allowed.values()) + [tid]
    conn.execute(f'UPDATE tasks SET {sets} WHERE id=?', vals)
    conn.commit()
    task = dict(conn.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone())
    conn.close()

    try:
        new_due  = task.get('due_date', '')
        event_id = task.get('gcal_event_id', '')
        if new_due:
            if event_id:
                _update_cal_event(current_user.id, event_id, task)
            else:
                new_id = _create_cal_event(current_user.id, task)
                if new_id:
                    conn2 = get_db()
                    conn2.execute('UPDATE tasks SET gcal_event_id=? WHERE id=?', (new_id, tid))
                    conn2.commit()
                    conn2.close()
                    task['gcal_event_id'] = new_id
        elif not new_due and event_id:
            _delete_cal_event(current_user.id, event_id)
            conn2 = get_db()
            conn2.execute('UPDATE tasks SET gcal_event_id="" WHERE id=?', (tid,))
            conn2.commit()
            conn2.close()
            task['gcal_event_id'] = ''
    except Exception as e:
        print(f'Calendar update error: {e}')

    return jsonify(task)

@app.route('/api/tasks/<int:tid>', methods=['DELETE'])
@login_required
def delete_task(tid):
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id=? AND user_id=?',
                         (tid, current_user.id)).fetchone()
    if task and task['gcal_event_id']:
        try:
            _delete_cal_event(current_user.id, task['gcal_event_id'])
        except Exception as e:
            print(f'Calendar delete error: {e}')
    conn.execute('DELETE FROM tasks WHERE id=? AND user_id=?', (tid, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════════════════════════
# GOOGLE CALENDAR OAUTH
# ═══════════════════════════════════════════════════════════════

def _gcal_client_config():
    return {
        'web': {
            'client_id':     GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'auth_uri':      'https://accounts.google.com/o/oauth2/auth',
            'token_uri':     'https://oauth2.googleapis.com/token',
            'redirect_uris': [GOOGLE_REDIRECT_URI],
        }
    }

@app.route('/auth/google/start')
@login_required
def google_auth_start():
    if not GOOGLE_AVAILABLE:
        return redirect(url_for('index'))
    flow = Flow.from_client_config(_gcal_client_config(), scopes=GOOGLE_SCOPES)
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    auth_url, state  = flow.authorization_url(access_type='offline', prompt='consent')
    session['gcal_state'] = state
    return redirect(auth_url)

@app.route('/auth/google/callback')
@login_required
def google_auth_callback():
    if not GOOGLE_AVAILABLE:
        return redirect(url_for('index'))
    try:
        flow = Flow.from_client_config(_gcal_client_config(), scopes=GOOGLE_SCOPES,
                                       state=session.get('gcal_state'))
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials

        # Get Google account email from tokeninfo
        google_email = ''
        try:
            import urllib.request
            with urllib.request.urlopen(
                f'https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={creds.token}'
            ) as resp:
                google_email = json.loads(resp.read()).get('email', '')
        except Exception:
            pass

        token_json = {
            'token':         creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri':     creds.token_uri,
            'client_id':     creds.client_id,
            'client_secret': creds.client_secret,
            'scopes':        list(creds.scopes) if creds.scopes else GOOGLE_SCOPES,
            'expiry':        creds.expiry.isoformat() if creds.expiry else None,
        }
        conn = get_db()
        conn.execute('INSERT OR REPLACE INTO google_tokens (user_id, token_json, google_email) '
                     'VALUES (?,?,?)', (current_user.id, json.dumps(token_json), google_email))
        conn.commit()
        conn.close()
        return redirect(url_for('index') + '?gcal=connected')
    except Exception as e:
        print(f'Google OAuth callback error: {e}')
        return redirect(url_for('index') + '?gcal=error')

@app.route('/auth/google/disconnect')
@login_required
def google_auth_disconnect():
    conn = get_db()
    conn.execute('DELETE FROM google_tokens WHERE user_id=?', (current_user.id,))
    conn.execute('UPDATE tasks SET gcal_event_id="" WHERE user_id=?', (current_user.id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# ═══════════════════════════════════════════════════════════════
# GOOGLE CALENDAR HELPERS
# ═══════════════════════════════════════════════════════════════

def _get_cal_service(user_id):
    if not GOOGLE_LIBS:
        return None
    conn = get_db()
    row  = conn.execute('SELECT token_json FROM google_tokens WHERE user_id=?', (user_id,)).fetchone()
    conn.close()
    if not row:
        return None

    td    = json.loads(row['token_json'])
    expiry = None
    if td.get('expiry'):
        try:
            expiry = datetime.fromisoformat(td['expiry'])
        except Exception:
            pass

    creds = Credentials(
        token=td.get('token'),
        refresh_token=td.get('refresh_token'),
        token_uri=td.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=td.get('scopes', GOOGLE_SCOPES),
        expiry=expiry,
    )
    if not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
            td['token']  = creds.token
            td['expiry'] = creds.expiry.isoformat() if creds.expiry else None
            conn2 = get_db()
            conn2.execute('UPDATE google_tokens SET token_json=? WHERE user_id=?',
                          (json.dumps(td), user_id))
            conn2.commit()
            conn2.close()
        except Exception as e:
            print(f'Token refresh error: {e}')
            return None
    return build('calendar', 'v3', credentials=creds)

def _task_to_event(task):
    due = task.get('due_date', '')
    if not due:
        return None
    end = (datetime.strptime(due, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    pri = task.get('priority', 'none')
    cat = task.get('category', 'general')
    desc = task.get('description', '') or ''
    if pri != 'none':
        prefix = f'Priority: {pri.title()} | Category: {cat.title()}\n\n'
        desc   = (prefix + desc).strip()
    event = {
        'summary':     task.get('title', 'Task'),
        'description': desc,
        'start':       {'date': due},
        'end':         {'date': end},
    }
    color = {'high': '11', 'medium': '5', 'low': '10'}.get(pri)
    if color:
        event['colorId'] = color
    return event

def _create_cal_event(user_id, task):
    svc   = _get_cal_service(user_id)
    event = _task_to_event(task)
    if not svc or not event:
        return None
    result = svc.events().insert(calendarId='primary', body=event).execute()
    return result.get('id')

def _update_cal_event(user_id, event_id, task):
    svc   = _get_cal_service(user_id)
    event = _task_to_event(task)
    if not svc or not event or not event_id:
        return
    try:
        svc.events().update(calendarId='primary', eventId=event_id, body=event).execute()
    except Exception:
        pass

def _delete_cal_event(user_id, event_id):
    svc = _get_cal_service(user_id)
    if not svc or not event_id:
        return
    try:
        svc.events().delete(calendarId='primary', eventId=event_id).execute()
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# EMAIL REMINDERS
# ═══════════════════════════════════════════════════════════════

def _send_reminder_email(to_email, tasks):
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        return
    rows = ''.join(
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #2a2a50">{t["title"]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #2a2a50">{t["due_date"]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #2a2a50">{t["priority"].title()}</td>'
        f'</tr>'
        for t in tasks
    )
    html = f'''
    <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;background:#0d0d1a;
                padding:24px;border-radius:12px;color:#e8e8f5">
      <div style="background:linear-gradient(135deg,#6c63ff,#8b85ff);padding:20px;
                  border-radius:8px;text-align:center;margin-bottom:20px">
        <h1 style="color:#fff;margin:0;font-size:22px">&#9889; TaskPulse Reminder</h1>
      </div>
      <p style="font-size:15px">You have <strong>{len(tasks)}</strong> task(s) due soon:</p>
      <table style="width:100%;border-collapse:collapse;background:#1e1e3a;
                    border-radius:8px;overflow:hidden;margin:16px 0">
        <tr style="background:#6c63ff;color:#fff">
          <th style="padding:10px 12px;text-align:left">Task</th>
          <th style="padding:10px 12px;text-align:left">Due Date</th>
          <th style="padding:10px 12px;text-align:left">Priority</th>
        </tr>
        {rows}
      </table>
      <p style="color:#5555aa;font-size:12px;text-align:center;margin-top:16px">
        Sent by TaskPulse &middot;
        <a href="http://localhost:5000" style="color:#6c63ff">Open app</a>
      </p>
    </div>
    '''
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'TaskPulse: {len(tasks)} task(s) due soon'
    msg['From']    = GMAIL_SENDER
    msg['To']      = to_email
    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_SENDER, to_email, msg.as_string())

def _check_reminders():
    today    = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn     = get_db()
    users    = conn.execute(
        "SELECT id, email FROM users WHERE email != '' AND email IS NOT NULL"
    ).fetchall()
    for user in users:
        tasks = conn.execute(
            'SELECT id, title, due_date, priority FROM tasks '
            'WHERE user_id=? AND completed=0 AND reminder_sent=0 AND due_date IN (?,?)',
            (user['id'], today, tomorrow)
        ).fetchall()
        if tasks:
            try:
                _send_reminder_email(user['email'], [dict(t) for t in tasks])
                ids = [t['id'] for t in tasks]
                conn.execute(
                    f'UPDATE tasks SET reminder_sent=1 WHERE id IN ({",".join("?"*len(ids))})', ids
                )
                conn.commit()
                print(f"Reminder sent to {user['email']} for {len(tasks)} task(s)")
            except Exception as e:
                print(f"Reminder failed for {user['email']}: {e}")
    conn.close()

def _reminder_loop():
    time.sleep(5)  # brief delay so server is fully up first
    while True:
        try:
            _check_reminders()
        except Exception as e:
            print(f'Reminder loop error: {e}')
        time.sleep(3600)

# ═══════════════════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    init_db()
    threading.Thread(target=_reminder_loop, daemon=True).start()
    print('\n  TaskPulse is running!')
    print('  Open http://localhost:5000 in your browser')
    print('  Press Ctrl+C to stop\n')
    app.run(debug=False, port=5000)
