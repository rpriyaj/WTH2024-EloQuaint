from flask import Flask, request, jsonify, send_file, render_template, session, redirect, url_for
from flask_cors import CORS
import sqlite3
import hashlib
import os
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import logging
import whisper

# Initialize Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "super_secret_key"  # Replace with a strong secret key
CORS(app)

# Logging
logging.basicConfig(level=logging.INFO)

# Whisper model
logging.info("Loading Whisper model...")
model = whisper.load_model("base")

# Directories
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
FONT_FOLDER = "fonts"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Register dotted font
dotted_font_path = os.path.join(FONT_FOLDER, "KGPrimaryDots.ttf")
if os.path.exists(dotted_font_path):
    pdfmetrics.registerFont(TTFont("DottedFont", dotted_font_path))
else:
    logging.warning("Dotted font not found. PDF generation will fail.")

# Helper functions for user authentication
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def add_user(username, password):
    try:
        connection = sqlite3.connect("Users.db")
        cursor = connection.cursor()
        hashed_password = hash_password(password)

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            INSERT INTO Users (username, password)
            VALUES (?, ?)
        ''', (username, hashed_password))
        connection.commit()
        return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        connection.close()

def verify_user(username, password):
    try:
        connection = sqlite3.connect("Users.db")
        cursor = connection.cursor()
        hashed_password = hash_password(password)

        cursor.execute('''
            SELECT * FROM Users WHERE username = ? AND password = ?
        ''', (username, hashed_password))
        user = cursor.fetchone()
        return user is not None
    except sqlite3.Error:
        return False
    finally:
        connection.close()
        

# Routes
@app.route("/login-page")
def login_page():
    """Serve the login/signup page."""
    return render_template("login.html")

@app.route("/")
def home():
    """Redirect to transcription page if logged in, else redirect to login."""
    if "user_id" in session:
        return render_template("index.html", username=session["username"])
    return redirect(url_for("login_page"))

@app.route("/signup", methods=["POST"])
def signup():
    """Handle user signup."""
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "All fields are required."}), 400

    success, message = add_user(username, password)
    if not success:
        return jsonify({"error": message}), 400

    return jsonify({"message": message}), 201

@app.route("/login", methods=["POST"])
def login():
    """Handle user login."""
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "All fields are required."}), 400

    if verify_user(username, password):
        session["user_id"] = username
        session["username"] = username
        return jsonify({"message": f"Welcome, {username}!"}), 200
    else:
        return jsonify({"error": "Invalid username or password."}), 401

@app.route("/logout", methods=["GET"])
def logout():
    """Log out the user."""
    session.clear()
    return redirect(url_for("login_page"))

@app.route("/transcribe-live", methods=["POST"])
def transcribe_live():
    """Handle live transcription of audio chunks."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio chunk provided"}), 400

    audio_chunk = request.files["audio"]
    file_path = os.path.join(UPLOAD_FOLDER, "temp_chunk.wav")
    audio_chunk.save(file_path)

    try:
        result = model.transcribe(file_path)
        transcription = result.get("text", "")
        logging.info(f"Transcription: {transcription}")
    except Exception as e:
        logging.error(f"Error during transcription: {e}")
        return jsonify({"error": "Transcription failed"}), 500
    finally:
        os.remove(file_path)

    return jsonify({"transcription": transcription}), 200


@app.route("/generate-practice-sheet", methods=["POST"])
def generate_practice_sheet():
    """Generate a handwriting practice sheet from transcription."""
    data = request.json
    if not data or "text" not in data or not data["text"].strip():
        return jsonify({"error": "No text provided or text is empty"}), 400

    text = data["text"]
    output_path = os.path.join(OUTPUT_FOLDER, "handwriting_practice.pdf")

    try:
        # Create PDF document
        doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
        styles = getSampleStyleSheet()
        dotted_style = styles["BodyText"]
        dotted_style.fontName = "DottedFont"
        dotted_style.fontSize = 24
        dotted_style.leading = 30  # Line spacing
        dotted_style.spaceAfter = 10  # Space between paragraphs

        story = []  # List to hold PDF elements

        # Split text into paragraphs and add to story
        for paragraph in text.split("\n"):
            if paragraph.strip():
                story.append(Paragraph(paragraph.upper(), dotted_style))
                story.append(Spacer(1, 12))  # Add spacing between paragraphs

        # Build the PDF
        doc.build(story)
        logging.info("PDF generated successfully.")
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        return jsonify({"error": "PDF generation failed"}), 500

    return jsonify({"pdf_path": "/download-practice-sheet"}), 200





@app.route("/download-practice-sheet", methods=["GET"])
def download_practice_sheet():
    """Serve the generated handwriting practice PDF."""
    pdf_path = os.path.join(OUTPUT_FOLDER, "handwriting_practice.pdf")
    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF not found"}), 404
    return send_file(pdf_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)



