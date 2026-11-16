from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='PARTICIPANT')
    status = db.Column(db.String(20), default='ACTIVE')
    profile = db.relationship('Profile', backref='user', uselist=False, cascade='all, delete-orphan')

class Profile(db.Model):
    __tablename__ = 'profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(100), nullable=False)
    avatar_url = db.Column(db.String(255), default='/static/avatar.png')

class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date_time = db.Column(db.String(100), nullable=False)
    time = db.Column(db.String(20), default='12:00')
    duration = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(100))
    max_participants = db.Column(db.Integer)
    invite_link = db.Column(db.String(255))
    status = db.Column(db.String(20), default='PLANNED')
    organizer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    materials = db.relationship('Material', backref='event', cascade='all, delete-orphan')

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    text = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.String(50), nullable=False)
    is_question = db.Column(db.Boolean, default=False)
    author = db.relationship('User', backref='messages')

class Complaint(db.Model):
    __tablename__ = 'complaints'
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    target_id = db.Column(db.Integer)
    type = db.Column(db.String(50), default='Жалоба на организатора')
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='PENDING')
    date = db.Column(db.String(50))

class Recording(db.Model):
    __tablename__ = 'recordings'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))
    title = db.Column(db.String(200), default='Запись мероприятия')
    date = db.Column(db.String(50), default='01.06.2026')
    url = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.Integer)
    status = db.Column(db.String(20), default='AVAILABLE')

class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))
    filename = db.Column(db.String(255), nullable=False)
    file_uri = db.Column(db.String(255), nullable=False)

class LogEntry(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    action = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
