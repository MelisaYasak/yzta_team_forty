from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Gömülü kullanıcı verisi (gizli)
users = {
    "doktor1": "1234",
    "hemsire2": "abcd", 
    "admin3": "admin",
    "danisman4": "9876"
}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in users and users[username] == password:
            return redirect(url_for("welcome", username=username))
        else:
            error = "❌ Kullanıcı adı veya şifre hatalı."
    return render_template("login.html", error=error)

@app.route("/edevlet")
def edevlet():
    return render_template("edevlet.html")

@app.route("/enabiz")
def enabiz():
    return render_template("enabiz.html")

@app.route("/edevlet-login", methods=["POST"])
def edevlet_login():
    tc_no = request.form["tc_no"]
    password = request.form["password"]
    
    # E-devlet doğrulama simülasyonu
    if tc_no and password:
        # Gerçek uygulamada burada TC kimlik doğrulaması yapılır
        return redirect(url_for("welcome", username="E-Devlet Kullanıcısı"))
    else:
        return render_template("edevlet.html", error="❌ TC Kimlik No veya şifre hatalı.")

@app.route("/enabiz-login", methods=["POST"])
def enabiz_login():
    tc_no = request.form["tc_no"]
    password = request.form["password"]
    
    # E-nabız doğrulama simülasyonu
    if tc_no and password:
        # Gerçek uygulamada burada e-nabız doğrulaması yapılır
        return redirect(url_for("welcome", username="E-Nabız Kullanıcısı"))
    else:
        return render_template("enabiz.html", error="❌ TC Kimlik No veya şifre hatalı.")

@app.route("/welcome/<username>")
def welcome(username):
    return render_template("assistant.html", username=username)

@app.route("/chat/<username>")
def chat(username):
    return render_template("chat.html", username=username)

@app.route("/appointments/<username>")
def appointments(username):
    return render_template("appointments.html", username=username)

@app.route("/medicine/<username>")
def medicine(username):
    return render_template("medicine.html", username=username)

@app.route("/lab-results/<username>")
def lab_results(username):
    return render_template("lab_results.html", username=username)

@app.route("/calendar/<username>")
def calendar(username):
    return render_template("calendar.html", username=username)

if __name__ == "__main__":
    app.run(debug=True)