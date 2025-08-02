from flask import render_template, request, redirect, url_for, Blueprint, session
import sqlite3


edevlet_page = Blueprint('edevlet_page',__name__)

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
    
    query = "SELECT name, tc_no, password, email FROM user WHERE id = ?"
    cursor.execute(query, (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "name":  row[0],
            "tc_no":  row[1],
            "password":  row[2],
            "email": row[3]
        }
    return None


@edevlet_page.route("/edevlet")
def edevlet():
    return render_template("edevlet.html")

@edevlet_page.route("/edevlet-login", methods=["POST"])
def edevlet_login():
    tc_no = request.form["tc_no"]
    password = request.form["password"]
    user_id = get_user_id_from_tc(tc_no)
    print(user_id)
    if user_id:
        user = get_user_from_id(user_id.get('id'))

        if user:
            # Burada demo amaçlı basit bir kontrol yapabilirsin
            if tc_no and password:
                if user.get('tc_no') == tc_no:
                    session['user'] = {
                        'id': user_id.get('id'),
                        'name': user.get('name'),
                        'tc_no': user.get('tc_no'),
                        'email': user.get('email')
                    }
                    print(session['user']['id'])
                    # Örneğin başarılıysa anasayfaya yönlendir veya kullanıcıyı doğrula
                    return redirect(url_for("app.welcome", username=session['user']['name'], user_id = session['user']['id']))
                else:
                    return render_template("edevlet.html", error="❌ TC Kimlik No veya şifre hatalı.")
            else:
                return render_template("edevlet.html", error="❌ TC Kimlik No veya şifre hatalı.")
        else:
            return render_template("edevlet.html", error="❌ TC Kimlik No veya şifre hatalı.")
    else:
        return render_template("edevlet.html", error="❌ TC Kimlik No veya şifre hatalı.") 
