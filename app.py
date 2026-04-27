"""
POPO 看板助手 - Flask 后端
数据存储：本地 JSON 文件（tasks.json）
"""
import os
import json
import copy
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS

app = Flask(__name__)
CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')
CORS(app, origins=CORS_ORIGINS.split(',') if CORS_ORIGINS != '*' else '*')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv('DATA_DIR', BASE_DIR)
DATABASE = os.path.join(DATA_DIR, 'kanban.db')

# OpenClaw Gateway（自动从环境变量读取）
GATEWAY_URL = os.getenv('OPENCLAW_GATEWAY_URL', 'http://localhost:18789')
GATEWAY_TOKEN = os.getenv('OPENCLAW_GATEWAY_TOKEN', '')
MODEL = os.getenv('MODEL', 'gpt-4o')
AUTOMATION_WEBHOOK_URL = os.getenv('OPENCLAW_AUTOMATION_WEBHOOK_URL', '').strip()
SILENT_PENDING_HOURS = 48
SILENT_IN_PROGRESS_HOURS = 24
DUE_SOON_HOURS = 24
AUTO_ARCHIVE_DAYS = 3
AUTOMATION_STATE_PRIORITY = ['overdue', 'due_soon', 'silent', 'reactivated', 'auto_archived']
ANALYZE_MAX_TEXT_CHARS = int(os.getenv('ANALYZE_MAX_TEXT_CHARS', '50000'))
REMARKS_MAX_LEN = int(os.getenv('REMARKS_MAX_LEN', '100000'))
STATUS_HISTORY_MAX = int(os.getenv('STATUS_HISTORY_MAX', '500'))

# ─── 数据库 ────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            due_date TEXT,
            source TEXT DEFAULT '',
            sender TEXT DEFAULT '',
            raw_text TEXT DEFAULT '',
            remarks TEXT DEFAULT '',
            status_history TEXT DEFAULT '[]',
            automation TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    db.commit()
    db.close()

def migrate_from_json():
    json_file = os.path.join(BASE_DIR, 'tasks.json')
    if not os.path.exists(json_file):
        return
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        if not tasks:
            return
        db = sqlite3.connect(DATABASE)
        for t in tasks:
            db.execute('''
                INSERT OR IGNORE INTO tasks (id, title, description, status, priority, due_date, source, sender, raw_text, remarks, status_history, automation, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                t.get('id'),
                t.get('title', ''),
                t.get('description', ''),
                t.get('status', 'pending'),
                t.get('priority', 'medium'),
                t.get('due_date'),
                t.get('source', ''),
                t.get('sender', ''),
                t.get('raw_text', ''),
                t.get('remarks', ''),
                json.dumps(t.get('status_history', []), ensure_ascii=False),
                json.dumps(t.get('automation', {}), ensure_ascii=False),
                t.get('created_at', datetime.now().isoformat()),
                t.get('updated_at', t.get('created_at', datetime.now().isoformat())),
            ))
        db.commit()
        db.close()
        print(f'✅ 已从 tasks.json 迁移 {len(tasks)} 条任务')
    except Exception as e:
        print(f'⚠️ 迁移 tasks.json 失败: {e}')

# ─── 存储读写 ────────────────────────────────────────────────

def load_tasks():
    db = get_db()
    rows = db.execute('SELECT * FROM tasks ORDER BY id').fetchall()
    tasks = []
    for row in rows:
        task = dict(row)
        task['status_history'] = json.loads(task.get('status_history', '[]'))
        task['automation'] = json.loads(task.get('automation', '{}'))
        tasks.append(task)
    return tasks

def save_tasks(tasks):
    db = get_db()
    db.execute('DELETE FROM tasks')
    for t in tasks:
        db.execute('''
            INSERT INTO tasks (id, title, description, status, priority, due_date, source, sender, raw_text, remarks, status_history, automation, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            t.get('id'),
            t.get('title', ''),
            t.get('description', ''),
            t.get('status', 'pending'),
            t.get('priority', 'medium'),
            t.get('due_date'),
            t.get('source', ''),
            t.get('sender', ''),
            t.get('raw_text', ''),
            t.get('remarks', ''),
            json.dumps(t.get('status_history', []), ensure_ascii=False),
            json.dumps(t.get('automation', {}), ensure_ascii=False),
            t.get('created_at', datetime.now().isoformat()),
            t.get('updated_at', t.get('created_at', datetime.now().isoformat())),
        ))
    db.commit()

def next_id(tasks):
    if tasks:
        return max([t['id'] for t in tasks], default=0) + 1
    db = get_db()
    row = db.execute('SELECT MAX(id) FROM tasks').fetchone()
    return (row[0] or 0) + 1


def parse_iso_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_due_deadline(value):
    """将截止日期解析为「截止时间」：仅 YYYY-MM-DD 时视为当日结束，避免截止日当天 0 点起被判逾期。"""
    if not value:
        return None
    s = str(value).strip()
    dt = parse_iso_datetime(s)
    if not dt:
        return None
    if len(s) <= 10 or 'T' not in s:
        d = dt.date()
        return datetime.combine(d, datetime.max.time().replace(microsecond=999999))
    return dt


def now_iso(now=None):
    return (now or datetime.now()).isoformat()


def sort_automation_states(states):
    unique = list(dict.fromkeys(states))
    return sorted(unique, key=lambda item: (
        AUTOMATION_STATE_PRIORITY.index(item)
        if item in AUTOMATION_STATE_PRIORITY else len(AUTOMATION_STATE_PRIORITY),
        item,
    ))


def ensure_automation_fields(task):
    automation = task.get('automation')
    if not isinstance(automation, dict):
        automation = {}
        task['automation'] = automation

    states = automation.get('state')
    if not isinstance(states, list):
        states = []

    reasons = automation.get('reason')
    if not isinstance(reasons, dict):
        reasons = {}

    notification_keys = automation.get('notification_keys')
    if not isinstance(notification_keys, list):
        notification_keys = []

    automation['state'] = sort_automation_states(states)
    automation['reason'] = reasons
    automation['updated_at'] = automation.get('updated_at')
    automation['archived_at'] = automation.get('archived_at')
    automation['reactivated_at'] = automation.get('reactivated_at')
    automation['last_notified_at'] = automation.get('last_notified_at')
    automation['notification_keys'] = notification_keys
    return automation


def _append_automation_state(states, reasons, state, reason):
    states.append(state)
    reasons[state] = reason


def evaluate_task_automation(task, now=None):
    now = now or datetime.now()
    automation = ensure_automation_fields(task)
    updated_at = parse_iso_datetime(task.get('updated_at')) or parse_iso_datetime(task.get('created_at')) or now
    due_raw = task.get('due_date')
    due_deadline = parse_due_deadline(due_raw)
    due_day = due_deadline.date() if due_deadline else None
    archived_at = parse_iso_datetime(automation.get('archived_at'))

    states = []
    reasons = {}

    if task.get('status') in ('pending', 'in_progress'):
        silent_threshold_hours = SILENT_PENDING_HOURS if task.get('status') == 'pending' else SILENT_IN_PROGRESS_HOURS
        if now - updated_at >= timedelta(hours=silent_threshold_hours):
            _append_automation_state(states, reasons, 'silent', 'silent')

        if due_deadline:
            if now > due_deadline:
                _append_automation_state(states, reasons, 'overdue', 'overdue')
            elif now.date() <= due_day and timedelta(0) < (due_deadline - now) <= timedelta(hours=DUE_SOON_HOURS):
                _append_automation_state(states, reasons, 'due_soon', 'due_soon')

    if task.get('status') == 'done':
        auto_archive_due = updated_at + timedelta(days=AUTO_ARCHIVE_DAYS)
        was_auto_archived = 'auto_archived' in automation.get('state', [])

        if now >= auto_archive_due:
            _append_automation_state(states, reasons, 'auto_archived', 'done_for_3_days')
        elif was_auto_archived and archived_at and updated_at > archived_at:
            _append_automation_state(states, reasons, 'reactivated', 'activity_after_archive')

    return {
        'states': sort_automation_states(states),
        'reasons': reasons,
    }


def collect_notification_events(before_task, after_task):
    before_automation = ensure_automation_fields(before_task)
    after_automation = ensure_automation_fields(after_task)
    before_states = set(before_automation.get('state', []))
    after_states = set(after_automation.get('state', []))
    new_states = [state for state in after_automation.get('state', []) if state not in before_states]
    events = []
    for state in new_states:
        events.append({
            'task_id': after_task.get('id'),
            'title': after_task.get('title'),
            'state': state,
            'reason': after_automation.get('reason', {}).get(state),
            'notification_key': f"{after_task.get('id')}:{state}:{after_automation.get('updated_at')}",
        })
    if not new_states and before_states != after_states:
        events.append({
            'task_id': after_task.get('id'),
            'title': after_task.get('title'),
            'state': 'state_changed',
            'reason': 'automation_state_changed',
            'notification_key': f"{after_task.get('id')}:state_changed:{after_automation.get('updated_at')}",
        })
    return events


def dispatch_openclaw_notifications(tasks, events, now=None):
    if not events:
        return []

    now = now or datetime.now()
    sent_events = []
    for event in events:
        task = next((item for item in tasks if item.get('id') == event.get('task_id')), None)
        if task is None:
            continue
        automation = ensure_automation_fields(task)
        notification_key = event['notification_key']
        if notification_key in automation['notification_keys']:
            continue
        delivered = True
        if AUTOMATION_WEBHOOK_URL:
            delivered = send_openclaw_notification(event)
        if not delivered:
            continue
        automation['notification_keys'].append(notification_key)
        automation['last_notified_at'] = now_iso(now)
        sent_events.append(event)
    return sent_events


def send_openclaw_notification(event):
    payload = json.dumps({'event': event}, ensure_ascii=False).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
    }
    if GATEWAY_TOKEN:
        headers['Authorization'] = f'Bearer {GATEWAY_TOKEN}'
    req = urllib.request.Request(
        AUTOMATION_WEBHOOK_URL,
        data=payload,
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception:
        return False


def apply_task_automation(task, now=None):
    now = now or datetime.now()
    before_task = copy.deepcopy(task)
    automation = ensure_automation_fields(task)
    evaluation = evaluate_task_automation(task, now)
    new_states = evaluation['states']
    new_reasons = evaluation['reasons']
    previous_states = set(automation.get('state', []))

    automation['state'] = new_states
    automation['reason'] = new_reasons
    automation['updated_at'] = now_iso(now)

    if 'auto_archived' in new_states:
        automation['archived_at'] = automation.get('archived_at') or now_iso(now)
    elif 'auto_archived' in previous_states:
        automation['archived_at'] = None

    if 'reactivated' in new_states:
        automation['reactivated_at'] = now_iso(now)

    task_changed = before_task.get('automation') != automation
    return {
        'task': task,
        'changed': task_changed,
        'events': collect_notification_events(before_task, task),
    }


def scan_all_tasks_for_automation(tasks, trigger_source='api', now=None):
    now = now or datetime.now()
    changed = False
    events = []
    for task in tasks:
        result = apply_task_automation(task, now)
        changed = changed or result['changed']
        for event in result['events']:
            event['trigger_source'] = trigger_source
            events.append(event)
    sent_events = dispatch_openclaw_notifications(tasks, events, now)
    if sent_events:
        changed = True
    return {
        'tasks': tasks,
        'changed': changed,
        'events': sent_events,
    }


def scan_and_maybe_save(tasks, trigger_source='api', now=None):
    result = scan_all_tasks_for_automation(tasks, trigger_source=trigger_source, now=now)
    if result['changed']:
        save_tasks(tasks)
    return result

# ─── 工具函数 ────────────────────────────────────────────────

def validate_task(data, partial=False):
    if not partial:
        if not data.get('title', '').strip():
            return False, 'title 为必填字段'
    if 'priority' in data and data['priority'] not in ('low', 'medium', 'high'):
        return False, 'priority 必须是 low/medium/high'
    if 'status' in data and data['status'] not in ('pending', 'in_progress', 'done'):
        return False, 'status 必须是 pending/in_progress/done'
    return True, None


def coerce_task_priority(value):
    if value in ('low', 'medium', 'high'):
        return value
    return 'medium'


def coerce_task_status(value):
    if value in ('pending', 'in_progress', 'done'):
        return value
    return 'pending'


def normalize_remarks(value):
    if value is None:
        return ''
    s = value if isinstance(value, str) else str(value)
    s = s.strip()
    if len(s) > REMARKS_MAX_LEN:
        return s[:REMARKS_MAX_LEN]
    return s


def get_status_history_list(task):
    h = task.get('status_history')
    return h if isinstance(h, list) else []


def append_status_transition(task, old_status, new_status, at_iso):
    if old_status == new_status:
        return
    hist = list(get_status_history_list(task))
    hist.append({'at': at_iso, 'from': old_status, 'to': new_status})
    if len(hist) > STATUS_HISTORY_MAX:
        hist = hist[-STATUS_HISTORY_MAX:]
    task['status_history'] = hist


def normalize_analyzed_candidates(raw):
    """将模型输出整理为统一的任务候选列表。"""
    if raw is None:
        return []
    if isinstance(raw, dict):
        inner = raw.get('tasks') or raw.get('items') or raw.get('candidates')
        if isinstance(inner, list):
            raw = inner
        else:
            return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, str):
            title = item.strip()
            if title:
                out.append({
                    'title': title,
                    'description': '',
                    'priority': 'medium',
                    'due_date': None,
                })
            continue
        if not isinstance(item, dict):
            continue
        title = (item.get('title') or item.get('name') or item.get('task') or '').strip()
        if not title:
            continue
        desc = item.get('description') or item.get('detail') or item.get('notes') or ''
        if not isinstance(desc, str):
            desc = str(desc) if desc is not None else ''
        desc = desc.strip()
        due = item.get('due_date') or item.get('due') or item.get('deadline')
        if due is not None and not isinstance(due, str):
            due = str(due).strip() or None
        if due:
            due = due[:32].strip() or None
        pr = coerce_task_priority(item.get('priority'))
        out.append({
            'title': title[:2000],
            'description': desc[:20000],
            'priority': pr,
            'due_date': due,
        })
    return out

def task_to_dict(t):
    automation = ensure_automation_fields(t)
    return {
        'id': t['id'],
        'title': t['title'],
        'description': t.get('description', ''),
        'status': t['status'],
        'priority': t['priority'],
        'due_date': t.get('due_date') or None,
        'source': t.get('source', ''),
        'sender': t.get('sender', ''),
        'raw_text': t.get('raw_text', ''),
        'remarks': normalize_remarks(t.get('remarks', '')),
        'status_history': get_status_history_list(t),
        'created_at': t['created_at'],
        'updated_at': t.get('updated_at', t['created_at']),
        'automation': {
            'state': automation.get('state', []),
            'reason': automation.get('reason', {}),
            'updated_at': automation.get('updated_at'),
            'archived_at': automation.get('archived_at'),
            'reactivated_at': automation.get('reactivated_at'),
            'last_notified_at': automation.get('last_notified_at'),
        },
    }

# ─── 路由 ───────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/completed')
def completed():
    return render_template('completed.html')

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    tasks = load_tasks()
    scan_and_maybe_save(tasks, trigger_source='get_tasks')
    return jsonify([task_to_dict(t) for t in tasks])

@app.route('/api/tasks/<int:task_id>', methods=['GET'])
def get_task(task_id):
    tasks = load_tasks()
    scan_and_maybe_save(tasks, trigger_source='get_task')
    t = next((t for t in tasks if t['id'] == task_id), None)
    if t is None:
        return jsonify({'error': '任务不存在'}), 404
    return jsonify(task_to_dict(t))

@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.get_json() or {}
    valid, err = validate_task(data, partial=False)
    if not valid:
        return jsonify({'error': err}), 400

    tasks = load_tasks()
    now = datetime.now().isoformat()
    initial_status = coerce_task_status(data.get('status', 'pending'))
    new_task = {
        'id': next_id(tasks),
        'title': data['title'].strip(),
        'description': data.get('description', '').strip(),
        'status': initial_status,
        'priority': data.get('priority', 'medium'),
        'due_date': data.get('due_date') or None,
        'source': data.get('source', '').strip(),
        'sender': data.get('sender', '').strip(),
        'raw_text': data.get('raw_text', '').strip(),
        'remarks': normalize_remarks(data.get('remarks', '')),
        'status_history': [{'at': now, 'from': None, 'to': initial_status}],
        'created_at': now,
        'updated_at': now,
    }
    tasks.append(new_task)
    scan_and_maybe_save(tasks, trigger_source='create_task')
    return jsonify(task_to_dict(new_task)), 201

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.get_json() or {}
    tasks = load_tasks()
    idx = next((i for i, t in enumerate(tasks) if t['id'] == task_id), None)
    if idx is None:
        return jsonify({'error': '任务不存在'}), 404

    valid, err = validate_task(data, partial=True)
    if not valid:
        return jsonify({'error': err}), 400

    t = tasks[idx]
    title = data.get('title', t['title'])
    if not title or not title.strip():
        return jsonify({'error': 'title 不能为空'}), 400

    old_status = coerce_task_status(t.get('status', 'pending'))
    new_status = coerce_task_status(data['status']) if 'status' in data else old_status
    updated_at = datetime.now().isoformat()
    if new_status != old_status:
        append_status_transition(t, old_status, new_status, updated_at)

    remarks = normalize_remarks(data['remarks']) if 'remarks' in data else normalize_remarks(t.get('remarks', ''))

    tasks[idx] = {
        **t,
        'title': title.strip(),
        'description': data.get('description', t['description']),
        'status': new_status,
        'priority': data.get('priority', t['priority']),
        # If client explicitly sends due_date (including empty/null), honor it.
        # Otherwise keep existing value.
        'due_date': (data.get('due_date') or None) if 'due_date' in data else t.get('due_date'),
        'source': data.get('source', t.get('source', '')),
        'sender': data.get('sender', t.get('sender', '')),
        'remarks': remarks,
        'status_history': get_status_history_list(t),
        'updated_at': updated_at,
    }
    scan_and_maybe_save(tasks, trigger_source='update_task')
    return jsonify(task_to_dict(tasks[idx]))

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    tasks = load_tasks()
    idx = next((i for i, t in enumerate(tasks) if t['id'] == task_id), None)
    if idx is None:
        return jsonify({'error': '任务不存在'}), 404
    tasks.pop(idx)
    save_tasks(tasks)
    return '', 204


@app.route('/api/tasks/automation/scan', methods=['POST'])
def automation_scan():
    tasks = load_tasks()
    result = scan_and_maybe_save(tasks, trigger_source='manual_scan')
    return jsonify({
        'scanned': len(tasks),
        'changed': 1 if result['changed'] else 0,
        'events': result['events'],
    })

@app.route('/api/tasks/batch', methods=['POST'])
def create_tasks_batch():
    data = request.get_json() or {}
    tasks_data = data.get('tasks', [])
    if not isinstance(tasks_data, list):
        return jsonify({'error': 'tasks 必须为数组'}), 400

    tasks = load_tasks()
    now = datetime.now().isoformat()
    created = 0
    for t in tasks_data:
        if not t.get('title', '').strip():
            continue
        st = coerce_task_status(t.get('status', 'pending'))
        tasks.append({
            'id': next_id(tasks),
            'title': t['title'].strip(),
            'description': t.get('description', '').strip(),
            'status': st,
            'priority': coerce_task_priority(t.get('priority', 'medium')),
            'due_date': t.get('due_date') or None,
            'source': t.get('source', '').strip(),
            'sender': t.get('sender', '').strip(),
            'raw_text': t.get('raw_text', '').strip(),
            'remarks': normalize_remarks(t.get('remarks', '')),
            'status_history': [{'at': now, 'from': None, 'to': st}],
            'created_at': now,
            'updated_at': now,
        })
        created += 1
    scan_and_maybe_save(tasks, trigger_source='batch_create')
    save_tasks(tasks)
    return jsonify({'created': created}), 201

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """AI 从聊天或长文本中识别任务候选。
    通过 OpenClaw Gateway 调用 AI（无需额外配置 API key）。"""
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'text 为必填字段'}), 400
    if len(text) > ANALYZE_MAX_TEXT_CHARS:
        return jsonify({
            'error': f'文本过长（上限 {ANALYZE_MAX_TEXT_CHARS} 字），请分段粘贴或调高环境变量 ANALYZE_MAX_TEXT_CHARS',
        }), 400

    prompt = f"""你是一个任务提取助手。请从下面用户提供的文本中提取所有可执行的待办任务。

文本可能是：聊天记录、会议纪要、需求脑暴、项目清单、邮件正文、编号/符号列表（如 1. / - / * / [ ]）等。

对于每个任务，返回：title（任务标题，简短可执行）、description（补充上下文，可为空字符串）、priority（low/medium/high）、due_date（若能从文中推断则为 YYYY-MM-DD，否则为 null）。

输出格式：仅输出一个 JSON 数组，不要输出其它说明文字：
[
  {{
    "title": "任务标题",
    "description": "任务详情或背景",
    "priority": "medium",
    "due_date": "2026-04-15"
  }},
  ...
]

规则：
- 将同一主题下的子步骤拆成多条独立任务（除非明显是一条任务的细分说明可合并进 description）
- 只提取明确的、可执行的行动项；纯提问、寒暄、无行动结论的讨论不提取
- 如果无法推断截止日期，due_date 设为 null
- 若没有可提取任务，返回空数组 []

用户文本如下：
{text}"""

    content = ''
    try:
        payload = {
            'model': MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.3,
        }
        req = urllib.request.Request(
            f'{GATEWAY_URL}/v1/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {GATEWAY_TOKEN}',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        content = result['choices'][0]['message']['content'].strip()
        if content.startswith('```'):
            lines = content.split('\n')
            content = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
        parsed = json.loads(content)
        candidates = normalize_analyzed_candidates(parsed)
        return jsonify({'candidates': candidates})
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        return jsonify({'error': f'AI 请求失败 ({e.code})', 'detail': body}), 500
    except json.JSONDecodeError:
        return jsonify({'error': 'AI 返回格式错误', 'raw': content[:8000]}), 500
    except Exception as e:
        return jsonify({'error': f'AI 调用失败: {str(e)}'}), 500

# ─── 初始化 ────────────────────────────────────────────────────

# 模块加载时初始化数据库（支持 gunicorn）
init_db()
migrate_from_json()

# ─── 启动 ────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5151'))
    debug = os.environ.get('FLASK_ENV') != 'production'
    print(f'✅ POPO 看板助手已启动')
    print(f'   数据库: {DATABASE}')
    print(f'   访问地址: http://localhost:{port}')
    try:
        app.run(host='0.0.0.0', port=port, debug=debug)
    except OSError as e:
        if getattr(e, 'errno', None) == errno.EADDRINUSE:
            alt = port + 1
            print(
                f'❌ 端口 {port} 已被占用（例如已有一个本应用在跑）。'
                f'可先结束旧进程，或换端口启动：PORT={alt} python app.py'
            )
        raise
