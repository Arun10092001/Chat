from main import app, db, Message, Room

with app.app_context():
    messages = Message.query.all()
    print(f"Total messages in DB: {len(messages)}")
    for m in messages:
        print(f"[{m.room_name}] {m.username}: {m.message}")
