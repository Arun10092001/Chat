from main import app, db, Message, Room

with app.app_context():
    print("Testing DB connection...")
    try:
        new_msg = Message(username="test_user", room_name="General", message="test_message")
        db.session.add(new_msg)
        db.session.commit()
        print("Message added.")
        
        messages = Message.query.all()
        print(f"Total messages in DB: {len(messages)}")
        for m in messages:
            print(f"[{m.room_name}] {m.username}: {m.message}")
    except Exception as e:
        import traceback
        traceback.print_exc()
