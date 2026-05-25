from datetime import datetime, date
from zoneinfo import ZoneInfo
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

BEIJING_TZ = ZoneInfo('Asia/Shanghai')


def beijing_now():
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    balance = db.Column(db.Float, default=100.0)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    schedules = db.relationship('Schedule', backref='user', lazy=True)
    checkins = db.relationship('CheckIn', backref='user', lazy=True)
    penalty_amount = db.Column(db.Float, default=10.0)
    bark_key = db.Column(db.String(256), nullable=True)
    makeup_tokens = db.Column(db.Integer, default=0)
    last_streak_award = db.Column(db.Integer, default=0)
    schedule_modified_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), default='我的计划')
    days = db.Column(db.String(50), nullable=False)  # JSON: [0,2,4] 0=Mon
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def get_days_list(self):
        import json
        return json.loads(self.days)

    def is_scheduled_day(self, check_date=None):
        if check_date is None:
            check_date = date.today()
        return check_date.weekday() in self.get_days_list()


class CheckIn(db.Model):
    __tablename__ = 'checkins'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    check_date = db.Column(db.Date, nullable=False, default=date.today)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    duration = db.Column(db.Integer, nullable=True)  # seconds
    status = db.Column(db.String(20), default='active')  # active/completed/missed
    created_at = db.Column(db.DateTime, default=datetime.now)

    def finish(self):
        self.end_time = beijing_now()
        if self.start_time:
            self.duration = int((self.end_time - self.start_time).total_seconds())
        self.status = 'completed'


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    to_type = db.Column(db.String(20), default='public')  # public/user
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    from_user = db.relationship('User', foreign_keys=[from_user_id])
    to_user = db.relationship('User', foreign_keys=[to_user_id])


class PublicAccount(db.Model):
    __tablename__ = 'public_account'
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.now)
