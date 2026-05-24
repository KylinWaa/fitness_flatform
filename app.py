import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, User, Schedule, CheckIn, Transaction, PublicAccount

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fitness-platform-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fitness.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

BARK_ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bark_icon.png')

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


@app.route('/bark-icon')
def serve_bark_icon():
    return send_file(BARK_ICON_FILE, mimetype='image/png')


def get_bark_icon_url():
    return url_for('serve_bark_icon', _external=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.before_request
def load_public_account():
    g.public_account = PublicAccount.query.first()
    if not g.public_account:
        g.public_account = PublicAccount(balance=0)
        db.session.add(g.public_account)
        db.session.commit()


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': '未登录'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': '未登录'}), 401
        if not current_user.is_admin:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated


def get_today():
    return date.today()


def get_weekday_name(d):
    names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return names[d]


# ─── BARK NOTIFICATION ────────────────────────────────────────────────────────

def send_bark(user, title, body=''):
    if not user.bark_key:
        return False
    try:
        encoded_title = urllib.parse.quote(title, safe='')
        encoded_icon = urllib.parse.quote(get_bark_icon_url(), safe='')
        url = f'https://api.day.app/{user.bark_key}/{urllib.parse.quote("锻体！", safe="")}/{encoded_title}?icon={encoded_icon}'
        if body:
            encoded_body = urllib.parse.quote(body, safe='')
            url += f'&body={encoded_body}'
        urllib.request.urlopen(url, timeout=5)
        return True
    except Exception:
        return False


def broadcast_bark(title, body=''):
    users = User.query.filter(User.bark_key.isnot(None), User.bark_key != '').all()
    for u in users:
        send_bark(u, title, body)


# ─── MAKEUP TOKEN ─────────────────────────────────────────────────────────────

def check_and_award_makeup(user):
    today = get_today()
    streak = 0
    d = today
    while True:
        c = CheckIn.query.filter_by(user_id=user.id, check_date=d, status='completed').first()
        if c:
            streak += 1
            d -= timedelta(days=1)
        else:
            break
    milestone = (streak // 7) * 7
    if milestone > user.last_streak_award and milestone >= 7:
        new_tokens = (milestone - user.last_streak_award) // 7
        user.makeup_tokens += new_tokens
        user.last_streak_award = milestone
        return new_tokens
    return 0


# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        flash('用户名或密码错误')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('用户名和密码不能为空')
        elif len(username) < 2 or len(username) > 20:
            flash('用户名长度需在 2-20 个字符之间')
        elif username.lower() == 'admin':
            flash('该用户名不可用')
        elif User.query.filter_by(username=username).first():
            flash('用户名已存在')
        else:
            user = User(username=username, balance=100.0)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─── PAGES ───────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    today = get_today()

    active_schedule = Schedule.query.filter_by(user_id=current_user.id, is_active=True).first()
    is_scheduled = active_schedule.is_scheduled_day(today) if active_schedule else False

    today_checkin = CheckIn.query.filter_by(
        user_id=current_user.id, check_date=today
    ).order_by(CheckIn.id.desc()).first()

    recent_checkins = CheckIn.query.filter_by(user_id=current_user.id)\
        .order_by(CheckIn.check_date.desc()).limit(7).all()

    total_completed = CheckIn.query.filter_by(user_id=current_user.id, status='completed').count()
    total_missed = CheckIn.query.filter_by(user_id=current_user.id, status='missed').count()

    streak = 0
    d = today - timedelta(days=1)
    while True:
        c = CheckIn.query.filter_by(user_id=current_user.id, check_date=d, status='completed').first()
        if c:
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    public_balance = g.public_account.balance if g.public_account else 0

    return render_template('dashboard.html',
                           today=today, is_scheduled=is_scheduled,
                           today_checkin=today_checkin, recent_checkins=recent_checkins,
                           total_completed=total_completed, total_missed=total_missed,
                           streak=streak, public_balance=public_balance)


@app.route('/checkin')
@login_required
def checkin_page():
    today = get_today()
    active_schedule = Schedule.query.filter_by(user_id=current_user.id, is_active=True).first()
    is_scheduled = active_schedule.is_scheduled_day(today) if active_schedule else False

    today_checkin = CheckIn.query.filter_by(
        user_id=current_user.id, check_date=today
    ).order_by(CheckIn.id.desc()).first()

    records = CheckIn.query.filter_by(user_id=current_user.id)\
        .order_by(CheckIn.check_date.desc()).limit(30).all()

    start_timestamp = 0
    if today_checkin and today_checkin.status == 'active' and today_checkin.start_time:
        start_timestamp = today_checkin.start_time.timestamp()

    return render_template('checkin.html',
                           today=today, is_scheduled=is_scheduled,
                           today_checkin=today_checkin, records=records,
                           start_timestamp=start_timestamp)


@app.route('/schedule')
@login_required
def schedule_page():
    schedules = Schedule.query.filter_by(user_id=current_user.id).order_by(Schedule.created_at.desc()).all()
    all_schedules = Schedule.query.filter_by(is_active=True).join(User).filter(
        User.username != 'admin'
    ).order_by(Schedule.created_at.desc()).all()
    today = get_today()
    last_mod = current_user.schedule_modified_at
    can_modify = True
    if last_mod and last_mod.year == today.year and last_mod.month == today.month:
        can_modify = False
    return render_template('schedule.html', schedules=schedules, all_schedules=all_schedules,
                           can_modify=can_modify, last_modified=last_mod)


@app.route('/rankings')
@login_required
def rankings():
    today = get_today()
    month_start = today.replace(day=1)

    users = User.query.filter(User.username != 'admin').all()
    ranking_data = []
    for u in users:
        schedule = Schedule.query.filter_by(user_id=u.id, is_active=True).first()
        total = CheckIn.query.filter_by(user_id=u.id, status='completed').count()
        missed = CheckIn.query.filter_by(user_id=u.id, status='missed').count()
        monthly_done = CheckIn.query.filter(
            CheckIn.user_id == u.id,
            CheckIn.status == 'completed',
            CheckIn.check_date >= month_start
        ).count()

        streak = 0
        d = today - timedelta(days=1)
        while True:
            c = CheckIn.query.filter_by(user_id=u.id, check_date=d, status='completed').first()
            if c:
                streak += 1
                d -= timedelta(days=1)
            else:
                break

        rate = (total / (total + missed) * 100) if (total + missed) > 0 else 0

        ranking_data.append({
            'user': u,
            'total': total,
            'missed': missed,
            'rate': round(rate, 1),
            'streak': streak,
            'monthly': monthly_done,
        })

    ranking_data.sort(key=lambda x: (-x['rate'], -x['streak'], -x['total']))

    return render_template('rankings.html', ranking_data=ranking_data, today=today)


@app.route('/records')
@login_required
def records_page():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    user_filter = request.args.get('user_id', type=int)
    status_filter = request.args.get('status', '')

    query = CheckIn.query
    if user_filter:
        query = query.filter_by(user_id=user_filter)
    if status_filter:
        query = query.filter_by(status=status_filter)

    total_count = query.count()
    records = query.order_by(CheckIn.check_date.desc(), CheckIn.created_at.desc())\
        .offset((page - 1) * per_page).limit(per_page).all()

    users = User.query.filter(User.username != 'admin').all()
    total_pages = (total_count + per_page - 1) // per_page

    return render_template('records.html', records=records, users=users,
                           total_count=total_count, page=page, total_pages=total_pages,
                           user_filter=user_filter, status_filter=status_filter)


@app.route('/battle')
@login_required
def battle():
    users = User.query.filter(User.username != 'admin').all()
    user_a_id = request.args.get('a', type=int)
    user_b_id = request.args.get('b', type=int)

    stats_a = stats_b = None
    user_a = user_b = None

    if user_a_id:
        user_a = User.query.get(user_a_id)
        stats_a = _get_user_stats(user_a) if user_a else None
    if user_b_id:
        user_b = User.query.get(user_b_id)
        stats_b = _get_user_stats(user_b) if user_b else None

    return render_template('battle.html', users=users,
                           user_a=user_a, user_b=user_b,
                           stats_a=stats_a, stats_b=stats_b)


@app.route('/transactions')
@login_required
def transactions():
    txs = Transaction.query.filter(
        (Transaction.from_user_id == current_user.id) |
        (Transaction.to_user_id == current_user.id)
    ).order_by(Transaction.created_at.desc()).limit(50).all()
    public_balance = g.public_account.balance if g.public_account else 0
    return render_template('transactions.html', transactions=txs, public_balance=public_balance)


# ─── API ─────────────────────────────────────────────────────────────────────

@app.route('/api/checkin/start', methods=['POST'])
@api_login_required
def api_checkin_start():
    today = get_today()
    existing = CheckIn.query.filter_by(
        user_id=current_user.id, check_date=today, status='active'
    ).first()
    if existing:
        return jsonify({'error': '今日已有进行中的打卡', 'checkin_id': existing.id}), 400

    active_schedule = Schedule.query.filter_by(user_id=current_user.id, is_active=True).first()
    is_scheduled = active_schedule.is_scheduled_day(today) if active_schedule else False

    c = CheckIn(user_id=current_user.id, check_date=today, start_time=datetime.now(), status='active')
    db.session.add(c)
    db.session.commit()

    send_bark(current_user, '🏋️ 开始打卡', f'{current_user.username} 在 {today} 开始了健身打卡')

    return jsonify({'ok': True, 'checkin_id': c.id, 'is_scheduled': is_scheduled})


@app.route('/api/checkin/end', methods=['POST'])
@api_login_required
def api_checkin_end():
    data = request.get_json() or {}
    checkin_id = data.get('checkin_id')
    if checkin_id:
        c = CheckIn.query.get(checkin_id)
        if not c or c.user_id != current_user.id:
            return jsonify({'error': '打卡记录不存在'}), 404
    else:
        today = get_today()
        c = CheckIn.query.filter_by(
            user_id=current_user.id, check_date=today, status='active'
        ).first()
        if not c:
            return jsonify({'error': '没有进行中的打卡'}), 400

    c.finish()
    tokens_awarded = check_and_award_makeup(current_user)
    db.session.commit()

    mins = c.duration // 60 if c.duration else 0
    msg = f'{current_user.username} 完成打卡，运动 {mins} 分钟'
    if tokens_awarded:
        msg += f'，获得 {tokens_awarded} 个补签道具！'
    send_bark(current_user, '✅ 打卡完成', msg)

    return jsonify({
        'ok': True, 'duration': c.duration, 'checkin_id': c.id,
        'tokens_awarded': tokens_awarded
    })


@app.route('/api/checkin/<int:checkin_id>', methods=['DELETE'])
@api_login_required
def api_checkin_delete(checkin_id):
    c = CheckIn.query.get(checkin_id)
    if not c or c.user_id != current_user.id:
        return jsonify({'error': '打卡记录不存在'}), 404
    if c.check_date != get_today():
        return jsonify({'error': '只能删除当天的打卡记录'}), 400

    db.session.delete(c)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/username=<username>/start', methods=['GET', 'POST'])
def api_public_checkin_start(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': '用户不存在', 'username': username}), 404

    today = get_today()
    existing = CheckIn.query.filter_by(
        user_id=user.id, check_date=today, status='active'
    ).first()
    if existing:
        return jsonify({'error': '今日已有进行中的打卡', 'checkin_id': existing.id}), 400

    active_schedule = Schedule.query.filter_by(user_id=user.id, is_active=True).first()
    is_scheduled = active_schedule.is_scheduled_day(today) if active_schedule else False

    c = CheckIn(user_id=user.id, check_date=today, start_time=datetime.now(), status='active')
    db.session.add(c)
    db.session.commit()

    send_bark(user, '🏋️ 不打卡是给', f'{user.username} 在 {today} 开始了健身打卡')

    return jsonify({'ok': True, 'checkin_id': c.id, 'username': user.username, 'is_scheduled': is_scheduled})


@app.route('/api/username=<username>/end', methods=['GET', 'POST'])
def api_public_checkin_end(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': '用户不存在', 'username': username}), 404

    today = get_today()
    c = CheckIn.query.filter_by(
        user_id=user.id, check_date=today, status='active'
    ).first()
    if not c:
        return jsonify({'error': '没有进行中的打卡'}), 400

    c.finish()
    tokens_awarded = check_and_award_makeup(user)
    db.session.commit()

    mins = c.duration // 60 if c.duration else 0
    msg = f'{user.username} 完成打卡，运动 {mins} 分钟'
    if tokens_awarded:
        msg += f'，获得 {tokens_awarded} 个补签道具！'
    send_bark(user, '✅ 打卡完成', msg)

    return jsonify({
        'ok': True, 'duration': c.duration, 'checkin_id': c.id,
        'username': user.username, 'tokens_awarded': tokens_awarded
    })


@app.route('/api/schedule/update', methods=['POST'])
@api_login_required
def api_schedule_update():
    data = request.get_json()
    days = data.get('days', [])
    name = data.get('name', '我的计划')

    if not days:
        return jsonify({'error': '请选择至少一天'}), 400

    today = get_today()
    last_mod = current_user.schedule_modified_at
    if last_mod and last_mod.year == today.year and last_mod.month == today.month:
        return jsonify({'error': '本月已修改过计划，每月只能修改一次'}), 400

    days_json = json.dumps(sorted(days))

    Schedule.query.filter_by(user_id=current_user.id, is_active=True).update({'is_active': False})
    s = Schedule(user_id=current_user.id, name=name, days=days_json, is_active=True)
    db.session.add(s)
    current_user.schedule_modified_at = datetime.now()
    db.session.commit()
    return jsonify({'ok': True, 'schedule_id': s.id})


@app.route('/api/bark/bind', methods=['POST'])
@api_login_required
def api_bark_bind():
    data = request.get_json()
    bark_key = data.get('bark_key', '').strip()

    if not bark_key:
        current_user.bark_key = None
        db.session.commit()
        return jsonify({'ok': True, 'message': '已解绑 Bark 推送'})

    # 测试 Bark 连接
    try:
        test_title = urllib.parse.quote('健身打卡测试', safe='')
        test_body = urllib.parse.quote('Bark推送绑定成功', safe='')
        test_icon = urllib.parse.quote(get_bark_icon_url(), safe='')
        test_url = f'https://api.day.app/{bark_key}/{urllib.parse.quote("绑定测试", safe="")}/{test_title}?icon={test_icon}&body={test_body}'
        urllib.request.urlopen(test_url, timeout=10)
        current_user.bark_key = bark_key
        db.session.commit()
        return jsonify({'ok': True, 'message': '绑定成功，已发送测试推送'})
    except Exception as e:
        return jsonify({'error': f'Bark 连接失败: {str(e)}'}), 400


@app.route('/api/makeup/use', methods=['POST'])
@api_login_required
def api_makeup_use():
    data = request.get_json()
    target_date_str = data.get('date', '')

    if current_user.makeup_tokens <= 0:
        return jsonify({'error': '没有可用的补签道具'}), 400

    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': '日期格式无效，请使用 YYYY-MM-DD'}), 400

    today = get_today()
    if target_date >= today:
        return jsonify({'error': '只能补签过去的日期'}), 400
    if target_date < today - timedelta(days=30):
        return jsonify({'error': '只能补签 30 天内的日期'}), 400

    existing = CheckIn.query.filter_by(user_id=current_user.id, check_date=target_date, status='completed').first()
    if existing:
        return jsonify({'error': '该日期已有完成记录'}), 400

    current_user.makeup_tokens -= 1
    c = CheckIn(
        user_id=current_user.id,
        check_date=target_date,
        start_time=datetime.combine(target_date, datetime.min.time()),
        end_time=datetime.combine(target_date, datetime.min.time()),
        duration=0,
        status='completed'
    )
    db.session.add(c)
    db.session.commit()

    send_bark(current_user, '🔧 补签成功', f'已补签 {target_date} 的打卡，剩余 {current_user.makeup_tokens} 个补签道具')

    return jsonify({'ok': True, 'makeup_tokens': current_user.makeup_tokens})


@app.route('/api/settlement/run', methods=['POST'])
@api_login_required
def api_settlement_run():
    today = get_today()
    results = []

    users = User.query.filter(User.username != 'admin').all()
    for u in users:
        schedule = Schedule.query.filter_by(user_id=u.id, is_active=True).first()
        if not schedule or not schedule.is_scheduled_day(today):
            continue

        existing = CheckIn.query.filter_by(user_id=u.id, check_date=today).first()
        if existing:
            continue

        penalty = u.penalty_amount
        if u.balance < penalty:
            penalty = u.balance

        if penalty <= 0:
            continue

        u.balance -= penalty

        c = CheckIn(user_id=u.id, check_date=today, status='missed')
        db.session.add(c)

        public = PublicAccount.query.first()
        if not public:
            public = PublicAccount(balance=0)
            db.session.add(public)
            db.session.flush()
        public.balance += penalty

        t = Transaction(from_user_id=u.id, to_type='public', amount=penalty,
                        reason=f'未完成 {today} 的打卡计划')
        db.session.add(t)

        send_bark(u, '⚠️ fw为什么不打卡', f'{u.username} 今日未打卡，扣除 {penalty:.0f} 元，余额 {u.balance:.0f} 元')

        results.append({'username': u.username, 'penalty': penalty, 'balance': u.balance})

    db.session.commit()
    return jsonify({'ok': True, 'settled': len(results), 'details': results})


@app.route('/api/remind', methods=['POST'])
@api_login_required
def api_remind():
    """提醒所有设置了计划的用户打卡（晚8点调用）"""
    today = get_today()
    reminded = 0

    users = User.query.filter(User.bark_key.isnot(None), User.bark_key != '').all()
    for u in users:
        schedule = Schedule.query.filter_by(user_id=u.id, is_active=True).first()
        if not schedule or not schedule.is_scheduled_day(today):
            continue

        existing = CheckIn.query.filter_by(user_id=u.id, check_date=today, status='completed').first()
        if existing:
            continue

        sent = send_bark(u, '⏰ byd要扣钱了', f'{u.username}，今天是计划打卡日，记得完成打卡哦！')
        if sent:
            reminded += 1

    return jsonify({'ok': True, 'reminded': reminded})


@app.route('/api/transfer', methods=['POST'])
@api_login_required
def api_transfer():
    data = request.get_json()
    amount = data.get('amount', 0)
    to_type = data.get('to_type', 'public')
    to_user_id = data.get('to_user_id')

    if amount <= 0:
        return jsonify({'error': '金额必须大于 0'}), 400

    if current_user.balance < amount:
        return jsonify({'error': '余额不足'}), 400

    if to_type == 'user' and to_user_id:
        to_user = User.query.get(to_user_id)
        if not to_user:
            return jsonify({'error': '目标用户不存在'}), 404
        to_user.balance += amount
        current_user.balance -= amount
        t = Transaction(from_user_id=current_user.id, to_type='user',
                        to_user_id=to_user_id, amount=amount,
                        reason=data.get('reason', '转账'))
    elif to_type == 'public':
        public = PublicAccount.query.first()
        if not public:
            public = PublicAccount(balance=0)
            db.session.add(public)
            db.session.flush()
        current_user.balance -= amount
        public.balance += amount
        t = Transaction(from_user_id=current_user.id, to_type='public',
                        amount=amount, reason=data.get('reason', '转入公共账户'))
    else:
        return jsonify({'error': '无效的转账类型'}), 400

    db.session.add(t)
    db.session.commit()
    return jsonify({'ok': True, 'balance': current_user.balance, 'transaction_id': t.id})


@app.route('/api/stats/<int:user_id>')
@api_login_required
def api_stats(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({'error': '用户不存在'}), 404
    return jsonify(_get_user_stats(u))


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _get_user_stats(u):
    today = get_today()
    month_start = today.replace(day=1)
    total = CheckIn.query.filter_by(user_id=u.id, status='completed').count()
    missed = CheckIn.query.filter_by(user_id=u.id, status='missed').count()
    monthly = CheckIn.query.filter(
        CheckIn.user_id == u.id,
        CheckIn.status == 'completed',
        CheckIn.check_date >= month_start
    ).count()

    streak = 0
    d = today - timedelta(days=1)
    while True:
        c = CheckIn.query.filter_by(user_id=u.id, check_date=d, status='completed').first()
        if c:
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    rate = (total / (total + missed) * 100) if (total + missed) > 0 else 0

    total_duration = db.session.query(db.func.sum(CheckIn.duration)).filter(
        CheckIn.user_id == u.id, CheckIn.status == 'completed'
    ).scalar() or 0

    return {
        'username': u.username,
        'balance': u.balance,
        'total': total, 'missed': missed, 'monthly': monthly,
        'streak': streak, 'rate': round(rate, 1),
        'total_duration': total_duration,
        'makeup_tokens': u.makeup_tokens,
    }


@app.context_processor
def inject_globals():
    pa = PublicAccount.query.first()
    return {
        'today': get_today(),
        'weekday_names': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
        'current_year': datetime.now().year,
        'global_public_balance': pa.balance if pa else 0,
    }


# ─── ADMIN ───────────────────────────────────────────────────────────────────


@app.route('/admin')
@login_required
def admin_page():
    if not current_user.is_admin:
        flash('需要管理员权限')
        return redirect(url_for('dashboard'))
    users = User.query.order_by(User.id).all()
    return render_template('admin.html', users=users)


@app.route('/admin/user/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': '不能删除自己'}), 400
    u = User.query.get(user_id)
    if not u:
        return jsonify({'error': '用户不存在'}), 404
    CheckIn.query.filter_by(user_id=user_id).delete()
    Schedule.query.filter_by(user_id=user_id).delete()
    Transaction.query.filter_by(from_user_id=user_id).delete()
    Transaction.query.filter_by(to_user_id=user_id).delete()
    db.session.delete(u)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/user/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def admin_toggle_admin(user_id):
    if user_id == current_user.id:
        return jsonify({'error': '不能修改自己的管理员状态'}), 400
    u = User.query.get(user_id)
    if not u:
        return jsonify({'error': '用户不存在'}), 404
    admin_count = User.query.filter_by(is_admin=True).count()
    if u.is_admin and admin_count <= 1:
        return jsonify({'error': '不能取消最后一个管理员'}), 400
    u.is_admin = not u.is_admin
    db.session.commit()
    return jsonify({'ok': True, 'is_admin': u.is_admin})


@app.route('/admin/user/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def admin_reset_password(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({'error': '用户不存在'}), 404
    u.set_password('123456')
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/user/<int:user_id>/edit', methods=['POST'])
@admin_required
def admin_edit_user(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({'error': '用户不存在'}), 404
    data = request.get_json()
    if 'balance' in data and data['balance'] is not None:
        u.balance = float(data['balance'])
    if 'penalty' in data and data['penalty'] is not None:
        u.penalty_amount = float(data['penalty'])
    db.session.commit()
    return jsonify({'ok': True, 'balance': u.balance, 'penalty': u.penalty_amount})


@app.route('/admin/user/<int:user_id>/reset-schedule', methods=['POST'])
@admin_required
def admin_reset_schedule(user_id):
    u = User.query.get(user_id)
    if not u:
        return jsonify({'error': '用户不存在'}), 404
    Schedule.query.filter_by(user_id=user_id).update({'is_active': False})
    u.schedule_modified_at = None
    db.session.commit()
    return jsonify({'ok': True})


def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', balance=100.0, is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
        if not PublicAccount.query.first():
            db.session.add(PublicAccount(balance=0))
        db.session.commit()


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
