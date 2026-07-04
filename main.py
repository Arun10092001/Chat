# import
import os
import random
import logging
from datetime import datetime
from typing import Dict

from flask import Flask, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask import redirect

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(24)

    _db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://chitchat_zyfl_user:f33t2d1DD1BsKSJb5HdfQt3Oe7ViV5wj@dpg-d8la23vavr4c73f5icm0-a.oregon-postgres.render.com/chitchat_zyfl")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = _db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEBUG = os.environ.get(
        "FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    CHAT_ROOMS = [
        "General",
        "Python",
        "Javascript",
        "Projects"
    ]


app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(100),
        nullable=False
    )

    room_name = db.Column(
        db.String(100),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


# handle reverse proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# socket_io
socketIO = SocketIO(
    app,
    cors_allowed_origins=app.config["CORS_ORIGINS"],
    async_mode='threading',
    logger=True,
    engineio_logger=True
)

# make a database/dict
active_users: Dict[str, dict] = {}

# make a user


def generate_username() -> str:
    timestamp = datetime.now().strftime('%H%M')
    return f"Guest({timestamp}){random.randint(1000, 9999)}"


@app.route("/")
def index():
    if 'username' not in session:
        return redirect("/login")

    return render_template(
        'index.html',
        username=session['username'],
        rooms=app.config["CHAT_ROOMS"]
    )


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:
            return render_template("register.html", error="Username already exists")

        user = User(
            username=username,
            password=generate_password_hash(password)
        )

        db.session.add(user)
        db.session.commit()

        return redirect("/login")

    message = request.args.get("message")
    return render_template("register.html", message=message)


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(
            username=username
        ).first()

        if not user:
            return redirect("/register?message=User+not+found.+Please+register.")

        if check_password_hash(
            user.password,
            password
        ):

            session["username"] = user.username

            return redirect("/")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


@socketIO.event
def connect():
    try:
        if 'username' not in session:
            return False

        active_users[request.sid] = {
            'username': session['username'],
            'connected_at': datetime.now().isoformat()
        }

        emit('active_users', {
            'users': [user['username'] for user in active_users.values()]
        }, broadcast=True)

        logger.info(f"User connected: {session['username']}")

    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return False


@socketIO.event
def disconnect():
    try:
        if request.sid in active_users:
            username = active_users[request.sid]['username']
            del active_users[request.sid]

            emit('active_users', {
                'users': [user['username'] for user in active_users.values()]
            }, broadcast=True)

            logger.info(f"User disconnected: {username}")

    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return False


@socketIO.on('set_username')
def set_username(data: dict):
    try:
        name = data.get('username')
        if not name:
            return {'status': 'error', 'message': 'Missing username'}

        if request.sid in active_users:
            active_users[request.sid]['username'] = name
        else:
            active_users[request.sid] = {
                'username': name,
                'connected_at': datetime.now().isoformat()
            }

        emit('active_users', {
            'users': [user['username'] for user in active_users.values()]
        }, broadcast=True)

        logger.info(f"Set username for sid {request.sid}: {name}")
        return {'status': 'ok'}

    except Exception as e:
        logger.error(f"Error in set_username: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@socketIO.on('join')
def on_join(data: dict):
    try:
        username = active_users.get(request.sid, {}).get(
            'username', session.get('username', generate_username()))
        room = data['room']

        if room not in app.config['CHAT_ROOMS']:
            logger.warning(f"No room available")
            return

        if request.sid not in active_users:
            active_users[request.sid] = {
                'username': username,
                'connected_at': datetime.now().isoformat()
            }

        join_room(room)
        messages = (
            Message.query
            .filter_by(room_name=room)
            .order_by(Message.created_at.asc())
            .all()
        )

        history = []

        for msg in messages:
            history.append({
                "username": msg.username,
                "message": msg.message
            })

        emit(
            "chat_history",
            {"messages": history}
        )
        active_users[request.sid]['room'] = room

        emit('status', {
            'msg': f"{username} has joined the room!",
            'type': 'join',
            'timestamp': datetime.now().isoformat()
        }, room=room)

        emit('active_users', {
            'users': [user['username'] for user in active_users.values()]
        }, broadcast=True)

        logger.info(f"User {username} has joined")

    except Exception as e:
        logger.error(str(e))


@socketIO.on('leave')
def on_leave(data: dict):
    try:
        username = active_users.get(request.sid, {}).get(
            'username', session.get('username', generate_username()))
        room = data['room']

        leave_room(room)
        if request.sid in active_users:
            active_users[request.sid].pop('room', None)

        emit('status', {
            'msg': f"{username} has left the room!",
            'type': 'leave',
            'timestamp': datetime.now().isoformat()
        }, room=room)

        emit('active_users', {
            'users': [user['username'] for user in active_users.values()]
        }, broadcast=True)

        logger.info(f"User {username} has left")

    except Exception as e:
        logger.error(str(e))


@socketIO.on('message')
def handle_message(data: dict):
    try:
        username = active_users.get(request.sid, {}).get(
            'username', session.get('username', generate_username()))
        room = data.get("room", 'General')
        msg_type = data.get('type', 'message')
        message = data.get('msg', "").strip()

        if not message:
            return

        timestamp = datetime.now().isoformat()

        if msg_type == "private":
            target_user = data.get('target')
            if not target_user:
                return

            for sid, user_data in active_users.items():
                if user_data['username'] == target_user:
                    new_message = Message(
                        username=username,
                        room_name=room,
                        message=message
                    )
                    print("Saving message:", message)
                    db.session.add(new_message)
                    db.session.commit()
                    print("Message saved successfully")
                    emit('private_message', {
                        'msg': message,
                        'from': username,
                        'to': target_user,
                        'timestamp': timestamp
                    }, room=sid)
                    emit('private_message', {
                        'msg': message,
                        'from': username,
                        'to': target_user,
                        'timestamp': timestamp
                    }, room=request.sid)
                    return

        else:
            if room not in app.config["CHAT_ROOMS"]:
                return

            new_message = Message(
                username=username,
                room_name=room,
                message=message
            )
            print("Saving message:", message)
            db.session.add(new_message)
            db.session.commit()
            print("Message saved successfully")

            emit('message', {
                'msg': message,
                'username': username,
                'room': room,
                'timestamp': timestamp
            }, room=room)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in handle_message: {str(e)}")
        import traceback
        traceback.print_exc()


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))

    socketIO.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=True,
        allow_unsafe_werkzeug=True
    )
