const socket = io();

let username = window.loggedInUsername || sessionStorage.getItem("username");

if (!username) {
  try {
    if (crypto && crypto.randomUUID) {
      username = `Guest(${new Date().toLocaleTimeString().replace(/:/g, "")})${crypto.randomUUID().slice(0, 4)}`;
    } else {
      username = `Guest(${new Date().toLocaleTimeString().replace(/:/g, "")})${Math.floor(Math.random() * 9000) + 1000}`;
    }
  } catch (e) {
    username = `Guest(${new Date().toLocaleTimeString().replace(/:/g, "")})${Math.floor(Math.random() * 9000) + 1000}`;
  }
  sessionStorage.setItem("username", username);
}

if (window.loggedInUsername) {
  username = window.loggedInUsername;
  sessionStorage.setItem("username", username);
}

// update server-rendered name in the UI (or fallback username)
const usernameEl = document.getElementById("username");
if (usernameEl) {
  usernameEl.textContent = username;
}
let currentRoom = "General";
const roomMessages = {};

socket.on("connect", () => {
  // inform server of this tab's username (per-tab)
  socket.emit("set_username", { username }, () => {
    joinRoom(currentRoom);
  });
});

socket.on("message", (data) => {
  console.log("MESSAGE EVENT:", data);
  addMessage(
    data.username,
    data.msg,
    data.username === username ? "own" : "other",
  );
});

socket.on("private_message", (data) => {
  addMessage(data.from, `[Private] ${data.msg}`, "private");
});

socket.on("status", (data) => {
  addMessage("System", data.msg, "system");
});

socket.on("active_users", (data) => {
  const userList = document.getElementById("active-users");
  userList.innerHTML = "";

  data.users.forEach((user) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "user-item";
    item.textContent = `${user}${user === username ? " (you)" : ""}`;
    item.addEventListener("click", () => insertPrivateMessage(user));
    userList.appendChild(item);
  });
});

socket.on("chat_history", (data) => {
  const chat = document.getElementById("chat");
  chat.innerHTML = "";

  roomMessages[currentRoom] = [];

  data.messages.forEach((msg) => {
    addMessage(
      msg.username,
      msg.message,
      msg.username === username ? "own" : "other",
    );
  });

  chat.scrollTop = chat.scrollHeight;
});

function addMessage(sender, message, type) {
  if (!roomMessages[currentRoom]) {
    roomMessages[currentRoom] = [];
  }

  roomMessages[currentRoom].push({ sender, message, type });

  const chat = document.getElementById("chat");
  const messageDiv = document.createElement("div");
  const senderSpan = document.createElement("span");
  const messageSpan = document.createElement("span");

  messageDiv.className = `message ${type}`;
  senderSpan.className = "message-sender";
  senderSpan.textContent = sender;
  messageSpan.textContent = message;

  messageDiv.append(senderSpan, messageSpan);
  chat.appendChild(messageDiv);
  chat.scrollTop = chat.scrollHeight;
}

function sendMessage() {
  const input = document.getElementById("message");
  const message = input.value.trim();

  if (!message) return;

  if (message.startsWith("@")) {
    const [target, ...msgParts] = message.substring(1).split(" ");
    const privateMsg = msgParts.join(" ").trim();

    if (privateMsg) {
      socket.emit("message", {
        msg: privateMsg,
        type: "private",
        target,
        room: currentRoom,
      });
      // show private message locally for the sender as an echoed private message
      addMessage(username, `[Private to ${target}] ${privateMsg}`, "private");
    }
  } else {
    socket.emit("message", {
      msg: message,
      room: currentRoom,
    });
  }

  input.value = "";
  input.focus();
}

function joinRoom(room) {
  if (room === currentRoom && roomMessages[room]) {
    return;
  }

  if (socket.connected && currentRoom !== room) {
    socket.emit("leave", { room: currentRoom });
  }

  currentRoom = room;
  socket.emit("join", { room });

  setActiveRoom(room);
}

function setActiveRoom(room) {
  document.querySelectorAll(".room-item").forEach((item) => {
    item.classList.toggle("active-room", item.textContent.trim() === room);
  });
}

function insertPrivateMessage(user) {
  const input = document.getElementById("message");
  input.value = `@${user} `;
  input.focus();
}

function handleKeyPress(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function logout() {
  window.location.href = "/logout";
}

document.addEventListener("DOMContentLoaded", () => {
  setActiveRoom(currentRoom);
});
