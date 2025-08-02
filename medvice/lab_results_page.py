from flask import Flask, render_template, request, redirect, url_for, Blueprint, session
import sqlite3
lab_results_page = Blueprint('lab_results_page',__name__)


def get_user_from_id(user_id):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()
    
    query = "SELECT name, tc_no, password FROM user WHERE tc_no = ?"
    cursor.execute(query, (user_id,))
    row = cursor.fetchalls()
    conn.close()
    
    if row:
        return {
            "name":  row[0],
            "tc_no":  row[1],
            "password":  row[2]
        }
    return None



def get_test_with_id(user_id):
    conn = sqlite3.connect(r'C:\\Users\\melis\\YZTA_m\\medvica\\yzta_team_forty\\medvice\\db\\db.db')
    cursor = conn.cursor()
    
    query = "SELECT id, test_type, test_name, value, unit, status, range_info, test_date FROM test_result WHERE user_id = ?"
    cursor.execute(query, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        results.append({
            "id": row[0], 
            "test_type": row[1], 
            "test_name": row[2], 
            "value": row[3], 
            "unit": row[4], 
            "status": row[5],
            "range_info": row[6], 
            "test_date": row[7],
        })
    return results

@lab_results_page.route("/lab-results/<int:user_id>")
def lab_results(user_id):

    results = get_test_with_id(user_id)
    return render_template("lab_results.html", user_id=user_id, lab_results=results)
