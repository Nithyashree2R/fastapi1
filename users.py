from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import jwt
import datetime
from fastapi import Cookie

app = FastAPI()

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

DATABASE = 'users.db'

# JWT secret key (should be stored securely)
app.config = {'JWT_SECRET_KEY': 'your_jwt_secret_key'}

# Function to create JWT token
def create_jwt_token(username):
    expiration_time = datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # Token valid for 1 hour
    payload = {
        'username': username,
        'exp': expiration_time
    }
    token = jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    return token

# Connect to the database (open on each request)
def get_db():
    db_connection = sqlite3.connect(DATABASE, check_same_thread=False)
    db_connection.row_factory = sqlite3.Row  # Enable access by column name
    return db_connection

# Route to register user
@app.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "action": "register"})

@app.post("/register", response_class=HTMLResponse)
async def post_register(request: Request, username: str = Form(...), password: str = Form(...)):
    message = None
    hashed_password = generate_password_hash(password)

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        db.commit()
        message = "User registered successfully!"
    except sqlite3.IntegrityError:
        message = "Username already exists."
    return templates.TemplateResponse("index.html", {"request": request, "message": message, "action": "register"})

# Route to login and generate JWT token
@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "action": "login"})

@app.post("/login", response_class=HTMLResponse)
async def post_login(request: Request, username: str = Form(...), password: str = Form(...)):
    message = None
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT password FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password):
        token = create_jwt_token(username)
        message = "Login successful. Welcome!"
        
        # Set the token as a cookie in the response
        response = templates.TemplateResponse("index.html", {"request": request, "message": message, "token": token, "action": "change-password"})
        response.set_cookie(key="jwt_token", value=token, httponly=True)  # Set token as HTTP-only cookie
        
        return response
    else:
        message = "Invalid username or password."
    return templates.TemplateResponse("index.html", {"request": request, "message": message, "action": "login"})

# Route to change password
@app.get("/change-password", response_class=HTMLResponse)
async def get_change_password(request: Request, token: str = Cookie(None)):
    if not token:
        return templates.TemplateResponse("index.html", {"request": request, "message": "Token is missing", "action": "login"})

    try:
        payload = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        username = payload['username']
    except jwt.ExpiredSignatureError:
        return templates.TemplateResponse("index.html", {"request": request, "message": "Expired token.", "action": "login"})
    
    return templates.TemplateResponse("index.html", {"request": request, "action": "change-password", "username": username})

@app.post("/change-password", response_class=HTMLResponse)
async def post_change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), token: str = Form(...)):
    message = None

    if not token:
        return templates.TemplateResponse("index.html", {"request": request, "message": "Token is missing", "action": "login"})
    
    try:
        payload = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        username = payload['username']
    except jwt.ExpiredSignatureError:
        message = "Expired token."
        return templates.TemplateResponse("index.html", {"request": request, "message": message, "action": "login"})
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT password FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], current_password):
        hashed_new_password = generate_password_hash(new_password)
        cursor.execute('UPDATE users SET password = ? WHERE username = ?', (hashed_new_password, username))
        db.commit()
        message = "Password changed successfully."
    else:
        message = "Incorrect current password."
    
    return templates.TemplateResponse("index.html", {"request": request, "message": message, "action": "change-password", "username": username})

# Initialize the database schema
@app.on_event("startup")
def startup():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(''' 
        CREATE TABLE IF NOT EXISTS users ( 
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT UNIQUE NOT NULL, 
            password TEXT NOT NULL 
        ) 
    ''')
    db.commit()

# Start the FastAPI app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
