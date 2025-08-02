# main.py

from flask import Flask, render_template
from chat import chat
from app import app
from medicine_page import medicine_page
from edevlet_page import edevlet_page
from enabiz_page import enabiz_page
from lab_results_page import lab_results_page
import os
from db.hospital import db, db_page

main = Flask(__name__)
main.secret_key = os.urandom(24)
# Blueprint'leri kaydet
main.register_blueprint(chat)
main.register_blueprint(app)
main.register_blueprint(medicine_page)
main.register_blueprint(edevlet_page)
main.register_blueprint(enabiz_page)
main.register_blueprint(lab_results_page)

@main.route('/')
def index():
    return render_template("index.html")


with db_page.app_context():
    db.create_all()
    print("Veritabanı oluşturuldu.")

if __name__ == '__main__':
    main.run(debug=True)
