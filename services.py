import datetime
import uuid
from models import User, Profile, Event, Message, Complaint, Recording, Material, LogEntry, UserRole, EventStatus, BroadcastStatus, db

class Logger:
    def log_action(self, user_id, action):
        entry = LogEntry(user_id=user_id, action=action, timestamp=str(datetime.datetime.now()))
        db.session.add(entry)
        db.session.commit()

    def log_error(self, error_text):
        entry = LogEntry(user_id=0, action=f"ERROR: {error_text}", timestamp=str(datetime.datetime.now()))
        db.session.add(entry)
        db.session.commit()

    def get_logs(self):
        return LogEntry.query.order_by(LogEntry.id.desc()).all()

class AuthService:
    def __init__(self, logger):
        self.logger = logger

    def register(self, email, password, name, role=UserRole.PARTICIPANT.value):
        if User.query.filter_by(email=email).first():
            return None
        user = User(email=email, password_hash=password, role=role)
        db.session.add(user)
        db.session.flush()
        profile = Profile(user_id=user.id, name=name)
        db.session.add(profile)
        db.session.commit()
        self.logger.log_action(user.id, f"User registered: {email}")
        return user

    def authenticate(self, email, password):
        user = User.query.filter_by(email=email).first()
        if user and user.password_hash == password and user.status == 'ACTIVE':
            self.logger.log_action(user.id, f"User authenticated: {email}")
            return user
        return None

    def validate_session(self, user_id):
        user = User.query.get(user_id)
        return user is not None and user.status == 'ACTIVE'

class EventSearchService:
    def get_upcoming_events(self):
        return Event.query.all()

    def search_by_name(self, query_str):
        return Event.query.filter(Event.title.contains(query_str)).all()

    def filter_by_category(self, category):
        if category == 'ALL' or not category:
            return Event.query.all()
        return Event.query.filter_by(category=category).all()

    def get_event_details(self, event_id):
        return Event.query.get_or_404(event_id)

class EventCreationService:
    def __init__(self, logger):
        self.logger = logger

    def create_event(self, data, organizer_id):
        slug = f"{uuid.uuid4().hex[:8]}"
        event = Event(
            title=data.get('title'),
            description=data.get('description'),
            date_time=data.get('date_time'),
            time=data.get('time', '12:00'),
            duration=int(data.get('duration', 60)),
            category=data.get('category'),
            max_participants=int(data.get('max_participants', 100)),
            invite_link=f"/event/join/{slug}",
            organizer_id=organizer_id,
            status=EventStatus.PLANNED.value
        )
        db.session.add(event)
        db.session.commit()
        self.logger.log_action(organizer_id, f"Created event: {event.title}")
        return event

    def edit_event(self, event_id, data):
        event = Event.query.get_or_404(event_id)
        event.title = data.get('title', event.title)
        event.description = data.get('description', event.description)
        event.date_time = data.get('date_time', event.date_time)
        event.time = data.get('time', event.time)
        if data.get('duration'):
            event.duration = int(data.get('duration'))
        if data.get('max_participants'):
            event.max_participants = int(data.get('max_participants'))
        if data.get('category'):
            event.category = data.get('category')
        db.session.commit()
        self.logger.log_action(event.organizer_id, f"Edited event: {event.title}")
        return event

    def cancel_event(self, event_id):
        event = Event.query.get_or_404(event_id)
        event.status = EventStatus.CANCELLED.value
        db.session.commit()
        self.logger.log_action(event.organizer_id, f"Cancelled event: {event.title}")

    def generate_invite_link(self, event_id):
        event = Event.query.get_or_404(event_id)
        return event.invite_link

    def save_statistics(self, event_id, stats):
        event = Event.query.get(event_id)
        title = event.title if event else 'Мероприятие'
        duration = event.duration if event else 60
        rec = Recording(
            event_id=event_id,
            title=title,
            date=str(datetime.datetime.now().strftime('%d.%m.%Y')),
            url=f"/recordings/{event_id}",
            duration=duration,
            status='AVAILABLE'
        )
        db.session.add(rec)
        db.session.commit()

class EventConnectionService:
    def check_available_seats(self, event_id):
        event = Event.query.get_or_404(event_id)
        return event.max_participants is None or event.max_participants > 0

    def join_event(self, event_id, user_id):
        return self.check_available_seats(event_id)

    def init_broadcast_connection(self, event_id):
        return f"wss://broadcast.server/stream/{event_id}"

class Chat:
    def __init__(self, event_id):
        self.chat_id = event_id
        self.event_id = event_id

    def send_message(self, user_id, text, is_question=False):
        msg = Message(
            event_id=self.event_id,
            author_id=user_id,
            text=text,
            sent_at=str(datetime.datetime.now()),
            is_question=is_question
        )
        db.session.add(msg)
        db.session.commit()
        return msg

    def get_messages(self):
        return Message.query.filter_by(event_id=self.event_id, is_question=False).all()

    def broadcast_message(self, message):
        return True

class BroadcastSubsystem:
    def __init__(self, event_id):
        self.broadcast_id = event_id
        self.event_id = event_id
        self.status = BroadcastStatus.IDLE.value
        self.chat = Chat(event_id)

    def start_stream(self):
        self.status = BroadcastStatus.LIVE.value

    def stop_stream(self):
        self.status = BroadcastStatus.ENDED.value

    def capture_video(self):
        return b""

    def capture_audio(self):
        return b""

    def transmit_to_participants(self):
        return True

    def handle_chat(self):
        return self.chat.get_messages()

    def share_screen(self):
        return True

    def show_whiteboard(self):
        return True

class BroadcastManagement:
    def __init__(self, logger):
        self.logger = logger

    def start_broadcast(self, event_id):
        subsystem = BroadcastSubsystem(event_id)
        subsystem.start_stream()
        event = Event.query.get_or_404(event_id)
        event.status = EventStatus.LIVE.value
        db.session.commit()
        self.logger.log_action(0, f"Broadcast started for event {event_id}")

    def stop_broadcast(self, event_id):
        subsystem = BroadcastSubsystem(event_id)
        subsystem.stop_stream()
        event = Event.query.get_or_404(event_id)
        event.status = EventStatus.COMPLETED.value
        db.session.commit()
        self.logger.log_action(0, f"Broadcast stopped for event {event_id}")

    def enable_screen_share(self, event_id):
        return BroadcastSubsystem(event_id).share_screen()

    def enable_whiteboard(self, event_id):
        return BroadcastSubsystem(event_id).show_whiteboard()

    def mute_participant(self, user_id):
        return True

    def disable_camera(self, user_id):
        return True

    def allow_question(self, user_id):
        return True

    def get_connected_participants(self, event_id):
        return User.query.filter_by(status='ACTIVE').all()

class ParticipantInteraction:
    def view_stream(self, event_id):
        return True

    def send_chat_message(self, event_id, author_id, text, is_question=False):
        chat = Chat(event_id)
        chat.send_message(author_id, text, is_question=is_question)

    def ask_question(self, event_id, author_id, question_text):
        self.send_chat_message(event_id, author_id, question_text, is_question=True)

    def toggle_microphone(self):
        return True

    def toggle_camera(self):
        return True

    def download_materials(self, material_id):
        mat = Material.query.get_or_404(material_id)
        return mat.file_uri

class ModerationService:
    def __init__(self, logger):
        self.logger = logger

    def manage_users(self):
        return User.query.all()

    def handle_complaint(self, complaint_id):
        c = Complaint.query.get_or_404(complaint_id)
        c.status = 'RESOLVED'
        db.session.commit()

    def monitor_server_load(self):
        return 24.5

    def force_stop_broadcast(self, event_id):
        event = Event.query.get_or_404(event_id)
        event.status = EventStatus.CANCELLED.value
        db.session.commit()
        self.logger.log_action(0, f"Force stopped broadcast for event {event_id}")

class HistoryService:
    def get_history(self, user_id):
        return Recording.query.all()

    def get_recording(self, recording_id):
        return Recording.query.get_or_404(recording_id)

class CoordinatorServer:
    def __init__(self, logger):
        self.logger = logger
        self.auth_service = AuthService(logger)
        self.event_search = EventSearchService()
        self.event_creation = EventCreationService(logger)
        self.event_connection = EventConnectionService()
        self.broadcast_mgmt = BroadcastManagement(logger)
        self.participant_interaction = ParticipantInteraction()
        self.moderation_service = ModerationService(logger)
        self.history_service = HistoryService()

    def route_request(self, request_path):
        self.logger.log_action(0, f"Routed request: {request_path}")
        return request_path

    def coordinate_subsystems(self):
        return True
