import sqlite3
from flask import Blueprint, render_template

# Blueprint olarak tanımlayın, Flask app değil
medicine_page = Blueprint('medicine_page', __name__)

def get_user_medicines(user_id):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()

    query = """
    SELECT um.id, um.user_id, um.medicine_id, um.favorited, um.ordered, um.timestamp,
           m.name, m.active_ingredient, m.manufacturer, m.price
    FROM user_medicine um
    JOIN medicine m ON um.medicine_id = m.id
    WHERE um.user_id = ?
    """
    cursor.execute(query, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "user_id": row[1],
            "medicine_id": row[2],
            "favorited": bool(row[3]),
            "ordered": bool(row[4]),
            "timestamp": row[5],
            "name": row[6],
            "activeIngredient": row[7],
            "manufacturer": row[8],
            "price": row[9],
        })
    return result

def get_user(user_id):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()
    
    query = "SELECT id, email, name FROM user WHERE id = ?"
    cursor.execute(query, (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "email": row[1],
            "name": row[2]
        }
    return None
@medicine_page.route('/medicines/<int:user_id>')
def user_medicines(user_id):
    medicines = get_user_medicines(user_id)
    user = get_user(user_id)
    
    print(f"Medicines data: {medicines}")
    print(f"User data: {user}")
    print(f"User id: {user_id}")
    
    if not user:
        return "Kullanıcı bulunamadı", 404
    
    return render_template('medicine.html', medicines=medicines, user=user, user_id=user_id)