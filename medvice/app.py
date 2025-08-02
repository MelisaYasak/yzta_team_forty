from flask import Flask, render_template, request, redirect, url_for, Blueprint, session
import sqlite3
app = Blueprint('app',__name__)

def get_user_id_from_tc(tc_no):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()
    
    query = "SELECT id FROM user WHERE tc_no = ?"
    cursor.execute(query, (tc_no,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0]
        }
    return None

def get_user_from_id(user_id):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()
    
    query = "SELECT name, tc_no, password FROM user WHERE tc_no = ?"
    cursor.execute(query, (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "name":  row[0],
            "tc_no":  row[1],
            "password":  row[2]
        }
    return None

def get_user_from_name(name):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()
    
    query = "SELECT id, name, tc_no, password FROM user WHERE name = ?"
    cursor.execute(query, (name,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "name":  row[1],
            "tc_no":  row[2],
            "password":  row[3]
        }
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = get_user_from_name(username)
        if username == user.get('name') and user.get('password')  == password:
            return redirect(url_for("welcome", username=username))
        else:
            error = "❌ Kullanıcı adı veya şifre hatalı."
    return render_template("login.html", error=error)

'''
DÜZENLENECEK
def get_test_with_id(user_id):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()
    
    query = "SELECT id, name, tc_no, password FROM user WHERE name = ?"
    cursor.execute(query, (name,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "name":  row[1],
            "tc_no":  row[2],
            "password":  row[3]
        }
    return None'''

@app.route("/welcome/<username>/<int:user_id>")
def welcome(username, user_id):
    return render_template("assistant.html", username=username, user_id = user_id)

@app.route("/chat/<int:user_id>")
def chat(user_id):
    return render_template("chat.html", user_id=user_id)

@app.route("/appointments/<int:user_id>")
def appointments(user_id):
    return render_template("appointments.html", user_id=user_id)

@app.route("/calendar/<int:user_id>")
def calendar(user_id):
    return render_template("calendar.html", user_id=user_id)
