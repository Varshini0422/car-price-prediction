from flask import (
    Flask, render_template, request, redirect,
    session, send_file, Response
)
import sqlite3
import pickle
import numpy as np
import io
import csv
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ----------------------------------
# App Configuration
# ----------------------------------
app = Flask(__name__)
app.secret_key = "car_price_prediction_secret"

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True

# ----------------------------------
# Load ML Model
# ----------------------------------
model = pickle.load(open("model/car_price_model.pkl", "rb"))

# ----------------------------------
# Load Car Names from Excel / CSV
# ----------------------------------
car_df = pd.read_csv("CAR DETAILS FROM CAR DEKHO.csv")
car_names = sorted(car_df["name"].dropna().unique())

# ----------------------------------
# Database Connection
# ----------------------------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# ----------------------------------
# Landing Page
# ----------------------------------
@app.route("/")
def landing():
    return render_template("landing.html")

# ----------------------------------
# Register
# ----------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )
            conn.commit()
        except:
            conn.close()
            return render_template("register.html", error=True)

        conn.close()
        return redirect("/login")

    return render_template("register.html")

# ----------------------------------
# Login
# ----------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        cursor = conn.cursor()

        user = cursor.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect("/predict")

        return render_template("login.html", error=True)

    return render_template("login.html")

# ----------------------------------
# Logout
# ----------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
# ----------------------------------
# Predict
# ----------------------------------
@app.route("/predict", methods=["GET", "POST"])
def predict():
    if "user_id" not in session:
        return redirect("/login")

    errors = {}

    if request.method == "POST":
        car_name = request.form.get("car_name")
        year = request.form.get("year")
        kms = request.form.get("kms")
        fuel = request.form.get("fuel")
        seller = request.form.get("seller")
        transmission = request.form.get("transmission")
        owner = request.form.get("owner")

        # ---------- VALIDATION ----------
        if not year:
            errors["year"] = "Year is required"
        else:
            year = int(year)
            if year < 1992 or year > 2020:
                errors["year"] = "Year must be between 1992 and 2020"

        if not kms:
            errors["kms"] = "Kilometers is required"
        else:
            kms = int(kms)
            if kms < 1 or kms > 806599:
                errors["kms"] = "Kilometers must be between 1 and 806,599"

        if not car_name:
            errors["car_name"] = "Please select a car"

        # ⛔ If validation fails → return form with errors
        if errors:
            return render_template(
                "index.html",
                car_names=car_names,
                errors=errors,
                form=request.form,
                active_page="predict"
            )

        # ---------- ENCODING ----------
        fuel_map = {0: 1, 1: 0, 2: 2}
        seller_map = {0: 0, 1: 1}
        transmission_map = {0: 0, 1: 1}

        fuel = fuel_map[int(fuel)]
        seller = seller_map[int(seller)]
        transmission = transmission_map[int(transmission)]
        owner = int(owner)

        input_data = pd.DataFrame([{
            "year": year,
            "km_driven": kms,
            "fuel": fuel,
            "seller_type": seller,
            "transmission": transmission,
            "owner": owner
        }])

        prediction_rupees = int(model.predict(input_data)[0])
        prediction_rupees = max(20000, min(prediction_rupees, 8900000))

        confidence = min(95, max(70, 90 - int(kms / 10000)))

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO predictions
            (user_id, car_name, car_year, kms_driven, fuel_type,
             seller_type, transmission, owner, predicted_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            car_name,
            year,
            kms,
            fuel,
            seller,
            transmission,
            owner,
            prediction_rupees
        ))
        conn.commit()
        conn.close()

        return render_template(
            "result.html",
            car_name=car_name,
            price=prediction_rupees,
            confidence=confidence,
            active_page="predict"
        )

    return render_template(
        "index.html",
        car_names=car_names,
        active_page="predict"
    )

# ----------------------------------
# History
# ----------------------------------
@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    data = cursor.execute(
        "SELECT * FROM predictions WHERE user_id=? ORDER BY date DESC",
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "history.html",
        data=data,
        active_page="history"
    )
# ----------------------------------
# Delete
# ----------------------------------
@app.route("/delete-prediction/<int:prediction_id>")
def delete_prediction(prediction_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    # Security: delete only user's own prediction
    cursor.execute("""
        DELETE FROM predictions
        WHERE id = ? AND user_id = ?
    """, (prediction_id, session["user_id"]))

    conn.commit()
    conn.close()

    return redirect("/history")


# ----------------------------------
# Export History CSV
# ----------------------------------
@app.route("/export-history")
def export_history():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT date, car_name, car_year, kms_driven, predicted_price
        FROM predictions
        WHERE user_id=?
        ORDER BY date DESC
    """, (session["user_id"],)).fetchall()
    conn.close()

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Car Name", "Year", "KMs", "Predicted Price"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for r in rows:
            writer.writerow([
                r["date"], r["car_name"], r["car_year"],
                r["kms_driven"], round(r["predicted_price"], 2)
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=prediction_history.csv"}
    )

# ----------------------------------
# Download PDF Report
# ----------------------------------
@app.route("/download-report")
def download_report():
    if "last_price" not in session:
        return redirect("/predict")

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, 800, "CarPrice AI – Valuation Report")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 760, f"Car Name: {session['last_car']}")
    pdf.drawString(50, 735, f"Estimated Price: ₹ {session['last_price']}")
    pdf.drawString(50, 710, f"Model Confidence: {session['last_confidence']}%")

    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="CarPrice_Report.pdf",
        mimetype="application/pdf"
    )
# ----------------------------------
# Dashboard
# ----------------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    # =========================
    # KPI STATS
    # =========================
    stats = cursor.execute("""
        SELECT 
            COUNT(*) AS total,
            AVG(predicted_price) AS avg_price,
            MAX(predicted_price) AS max_price,
            MIN(predicted_price) AS min_price
        FROM predictions
        WHERE user_id=?
    """, (session["user_id"],)).fetchone()

    total_count = stats["total"] or 0
    avg_price = round(stats["avg_price"], 2) if stats["avg_price"] else 0
    max_price = stats["max_price"] or 0
    min_price = stats["min_price"] or 0

    # =========================
    # AVG PRICE VS YEAR
    # =========================
    year_rows = cursor.execute("""
        SELECT car_year, AVG(predicted_price) AS avg_price
        FROM predictions
        WHERE user_id=?
        GROUP BY car_year
        ORDER BY car_year
    """, (session["user_id"],)).fetchall()

    year_labels = [int(r["car_year"]) for r in year_rows]
    year_prices = [round(float(r["avg_price"]), 2) for r in year_rows]

    # =========================
    # PRICE VS KILOMETERS
    # =========================
    kms_rows = cursor.execute("""
        SELECT kms_driven, predicted_price
        FROM predictions
        WHERE user_id=?
    """, (session["user_id"],)).fetchall()

    kms_points = [
        {"x": int(r["kms_driven"]), "y": float(r["predicted_price"])}
        for r in kms_rows
    ]

    # =========================
    # FUEL DISTRIBUTION
    # =========================
    fuel_rows = cursor.execute("""
        SELECT fuel_type, COUNT(*) AS cnt
        FROM predictions
        WHERE user_id=?
        GROUP BY fuel_type
    """, (session["user_id"],)).fetchall()

    fuel_labels = [int(r["fuel_type"]) for r in fuel_rows]
    fuel_counts = [int(r["cnt"]) for r in fuel_rows]

    # =========================
    # TRANSMISSION DISTRIBUTION
    # =========================
    trans_rows = cursor.execute("""
        SELECT transmission, COUNT(*) AS cnt
        FROM predictions
        WHERE user_id=?
        GROUP BY transmission
    """, (session["user_id"],)).fetchall()

    trans_labels = [int(r["transmission"]) for r in trans_rows]
    trans_counts = [int(r["cnt"]) for r in trans_rows]

    conn.close()

    return render_template(
        "dashboard.html",
        total_count=total_count,
        avg_price=avg_price,
        max_price=max_price,
        min_price=min_price,
        year_labels=year_labels,
        year_prices=year_prices,
        kms_points=kms_points,
        fuel_labels=fuel_labels,
        fuel_counts=fuel_counts,
        trans_labels=trans_labels,
        trans_counts=trans_counts,
        active_page="dashboard"
    )


# ----------------------------------
# Run App
# ----------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

