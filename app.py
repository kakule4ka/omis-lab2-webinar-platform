import os
import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Profile, Event, Message, Complaint, Recording, Material, LogEntry, UserRole, EventStatus
from services import Logger, CoordinatorServer

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'webinar_super_secret_key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///webinar.db'
    app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

    db.init_app(app)
    with app.app_context():
        db.create_all()

    logger = Logger()
    coordinator = CoordinatorServer(logger)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.route('/')
    def index():
        coordinator.route_request('/')
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        coordinator.route_request('/login')
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            user = coordinator.auth_service.authenticate(email, password)
            if user:
                if user.status == 'BLOCKED':
                    flash('Аккаунт заблокирован')
                else:
                    login_user(user)
                    return redirect(url_for('events'))
            else:
                flash('Неверный email или пароль')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        coordinator.route_request('/register')
        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password')
            role = request.form.get('role', UserRole.PARTICIPANT.value)
            user = coordinator.auth_service.register(email, password, name, role)
            if user:
                login_user(user)
                return redirect(url_for('events'))
            else:
                flash('Email уже занят')
        return render_template('register.html')

    @app.route('/events')
    @login_required
    def events():
        coordinator.route_request('/events')
        search = request.args.get('search', '')
        category = request.args.get('category', 'ALL')
        if search:
            event_list = coordinator.event_search.search_by_name(search)
        else:
            event_list = coordinator.event_search.filter_by_category(category)
        return render_template('events.html', events=event_list)

    @app.route('/my_events')
    @login_required
    def my_events():
        coordinator.route_request('/my_events')
        if current_user.role not in [UserRole.ORGANIZER.value, UserRole.ADMIN.value]:
            return redirect(url_for('events'))
        event_list = Event.query.filter_by(organizer_id=current_user.id).all()
        return render_template('my_events.html', events=event_list)

    @app.route('/event/<int:event_id>')
    @login_required
    def event_detail(event_id):
        coordinator.route_request(f'/event/{event_id}')
        event = coordinator.event_search.get_event_details(event_id)
        return render_template('event_detail.html', event=event)

    @app.route('/event/join/<path:slug>')
    @login_required
    def join_by_invite(slug):
        coordinator.route_request(f'/event/join/{slug}')
        event = Event.query.filter_by(invite_link=f'/event/join/{slug}').first_or_404()
        return redirect(url_for('event_detail', event_id=event.id))

    @app.route('/event/create', methods=['GET', 'POST'])
    @login_required
    def create_event():
        coordinator.route_request('/event/create')
        if current_user.role not in [UserRole.ORGANIZER.value, UserRole.ADMIN.value]:
            return redirect(url_for('events'))
        if request.method == 'POST':
            data = request.form.to_dict()
            event = coordinator.event_creation.create_event(data, current_user.id)

            file = request.files.get('material_file')
            if file and file.filename:
                filename = secure_filename(file.filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                mat = Material(event_id=event.id, filename=filename, file_uri=f"/static/uploads/{filename}")
                db.session.add(mat)
                db.session.commit()

            return redirect(url_for('my_events'))
        return render_template('create_event.html')

    @app.route('/event/edit/<int:event_id>', methods=['GET', 'POST'])
    @login_required
    def edit_event(event_id):
        coordinator.route_request(f'/event/edit/{event_id}')
        event = coordinator.event_search.get_event_details(event_id)
        if current_user.role not in [UserRole.ORGANIZER.value, UserRole.ADMIN.value] or (
            event.organizer_id != current_user.id and current_user.role != UserRole.ADMIN.value
        ):
            return redirect(url_for('events'))
        if request.method == 'POST':
            coordinator.event_creation.edit_event(event_id, request.form.to_dict())
            flash('Мероприятие обновлено')
            return redirect(url_for('my_events'))
        return render_template('edit_event.html', event=event)

    @app.route('/event/cancel/<int:event_id>')
    @login_required
    def cancel_event(event_id):
        coordinator.route_request(f'/event/cancel/{event_id}')
        event = coordinator.event_search.get_event_details(event_id)
        if current_user.role in [UserRole.ORGANIZER.value, UserRole.ADMIN.value] and (
            event.organizer_id == current_user.id or current_user.role == UserRole.ADMIN.value
        ):
            coordinator.event_creation.cancel_event(event_id)
            flash('Мероприятие отменено')
        return redirect(url_for('my_events'))

    @app.route('/broadcast/<int:event_id>')
    @login_required
    def broadcast(event_id):
        coordinator.route_request(f'/broadcast/{event_id}')
        if not coordinator.event_connection.join_event(event_id, current_user.id):
            flash('Свободных мест на мероприятие больше нет')
            return redirect(url_for('event_detail', event_id=event_id))
        coordinator.event_connection.init_broadcast_connection(event_id)

        event = coordinator.event_search.get_event_details(event_id)
        messages = Message.query.filter_by(event_id=event_id, is_question=False).all()
        questions = Message.query.filter_by(event_id=event_id, is_question=True).all()
        participants = coordinator.broadcast_mgmt.get_connected_participants(event_id)
        if current_user.role in [UserRole.ORGANIZER.value, UserRole.ADMIN.value]:
            return render_template('broadcast_organizer.html', event=event, messages=messages, questions=questions, participants=participants)
        else:
            return render_template('broadcast_participant.html', event=event, materials=event.materials, messages=messages)

    @app.route('/send_message/<int:event_id>', methods=['POST'])
    @login_required
    def send_message(event_id):
        text = request.form.get('text')
        if text:
            coordinator.participant_interaction.send_chat_message(event_id, current_user.id, text)
            logger.log_action(current_user.id, f"Chat message in event {event_id}: {text}")
        return redirect(url_for('broadcast', event_id=event_id))

    @app.route('/ask_question/<int:event_id>', methods=['POST'])
    @login_required
    def ask_question(event_id):
        text = request.form.get('question_text')
        if text:
            coordinator.participant_interaction.ask_question(event_id, current_user.id, text)
            logger.log_action(current_user.id, f"Question asked in event {event_id}: {text}")
            flash('Вопрос успешно отправлен организатору!')
        return redirect(url_for('broadcast', event_id=event_id))

    @app.route('/broadcast/start/<int:event_id>')
    @login_required
    def start_broadcast(event_id):
        if current_user.role in [UserRole.ORGANIZER.value, UserRole.ADMIN.value]:
            coordinator.broadcast_mgmt.start_broadcast(event_id)
        return redirect(url_for('broadcast', event_id=event_id))

    @app.route('/broadcast/stop/<int:event_id>')
    @login_required
    def stop_broadcast(event_id):
        if current_user.role in [UserRole.ORGANIZER.value, UserRole.ADMIN.value]:
            coordinator.broadcast_mgmt.stop_broadcast(event_id)
            coordinator.event_creation.save_statistics(event_id, {})
        return redirect(url_for('broadcast', event_id=event_id))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        coordinator.route_request('/profile')
        if request.method == 'POST':
            if current_user.profile:
                if request.form.get('name'):
                    current_user.profile.name = request.form.get('name')
            else:
                p = Profile(user_id=current_user.id, name=request.form.get('name', current_user.email))
                db.session.add(p)
            if request.form.get('email'):
                current_user.email = request.form.get('email')

            avatar_file = request.files.get('avatar_file')
            if avatar_file and avatar_file.filename:
                fname = secure_filename(avatar_file.filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                fpath = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                avatar_file.save(fpath)
                current_user.profile.avatar_url = f"/static/uploads/{fname}"

            new_pass = request.form.get('new_password')
            if new_pass and new_pass == request.form.get('confirm_password'):
                current_user.password_hash = new_pass
            db.session.commit()
            logger.log_action(current_user.id, "Profile updated")
            flash('Профиль обновлен')
        return render_template('profile.html')

    @app.route('/history')
    @login_required
    def history():
        coordinator.route_request('/history')
        recordings = coordinator.history_service.get_history(current_user.id)
        selected_rec_id = request.args.get('rec_id', type=int)
        selected_rec = Recording.query.get(selected_rec_id) if selected_rec_id else (recordings[0] if recordings else None)
        return render_template('history.html', recordings=recordings, selected_rec=selected_rec)

    @app.route('/complaint/create', methods=['POST'])
    @login_required
    def create_complaint():
        desc = request.form.get('description')
        if desc:
            c = Complaint(author_id=current_user.id, description=desc, date=str(datetime.datetime.now().strftime('%d.%m.%Y %H:%M')))
            db.session.add(c)
            db.session.commit()
            logger.log_action(current_user.id, f"Complaint created: {desc}")
            flash('Жалоба успешно отправлена администрации.')
        return redirect(url_for('events'))

    @app.route('/moderation')
    @login_required
    def moderation():
        coordinator.route_request('/moderation')
        if current_user.role != UserRole.ADMIN.value:
            return redirect(url_for('events'))
        users = coordinator.moderation_service.manage_users()
        complaints = Complaint.query.all()
        events = Event.query.all()
        load = coordinator.moderation_service.monitor_server_load()
        return render_template('moderation.html', users=users, complaints=complaints, events=events, server_load=load)

    @app.route('/moderation/logs')
    @login_required
    def moderation_logs():
        if current_user.role != UserRole.ADMIN.value:
            return redirect(url_for('events'))
        logs = logger.get_logs()
        return render_template('logs.html', logs=logs)

    @app.route('/user/block/<int:user_id>')
    @login_required
    def block_user(user_id):
        if current_user.role == UserRole.ADMIN.value:
            user = User.query.get_or_404(user_id)
            user.status = 'BLOCKED' if user.status == 'ACTIVE' else 'ACTIVE'
            db.session.commit()
            logger.log_action(current_user.id, f"User {user_id} status changed to {user.status}")
        return redirect(url_for('moderation'))

    @app.route('/complaint/resolve/<int:complaint_id>')
    @login_required
    def resolve_complaint(complaint_id):
        if current_user.role == UserRole.ADMIN.value:
            coordinator.moderation_service.handle_complaint(complaint_id)
            logger.log_action(current_user.id, f"Complaint {complaint_id} resolved")
        return redirect(url_for('moderation'))

    @app.route('/moderation/force_stop/<int:event_id>')
    @login_required
    def force_stop(event_id):
        if current_user.role == UserRole.ADMIN.value:
            coordinator.moderation_service.force_stop_broadcast(event_id)
        return redirect(url_for('moderation'))

    @app.route('/logout')
    @login_required
    def logout():
        coordinator.route_request('/logout')
        logout_user()
        return redirect(url_for('login'))

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
