from flask import Flask, render_template, request, redirect, url_for
import os
import pytesseract
from PIL import Image
import re
import cv2

app = Flask(__name__)

def resmi_iyilestir(dosya_yolu):
    img = cv2.imread(dosya_yolu)
    gri = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gri = cv2.resize(gri, None, fx=2, fy=2)
    gri = cv2.GaussianBlur(gri, (3, 3), 0)
    _, esik = cv2.threshold(gri, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return esik


def fis_bilgilerini_cek(ocr_text):
    tarih = re.search(r"\d{2}[./-]\d{2}[./-]\d{4}", ocr_text)
    tutarlar = re.findall(r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}", ocr_text)

    toplam = tutarlar[-1] if tutarlar else "Bulunamadı"

    return {
        "tarih": tarih.group() if tarih else "Bulunamadı",
        "toplam": toplam
    }

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    message = None
    ocr_text = None
    analiz = None

    if request.method == "POST":
        file = request.files.get("receipt")

        if file and file.filename != "":
            file_path = os.path.join("uploads", file.filename)
            file.save(file_path)

            temiz_resim = resmi_iyilestir(file_path)

            ocr_text = pytesseract.image_to_string(
                temiz_resim,
                lang="eng",
                config="--oem 3 --psm 6"
            )

            analiz = fis_bilgilerini_cek(ocr_text)

            message = "Fiş başarıyla yüklendi ve analiz edildi!"

    return render_template(
        "upload.html",
        message=message,
        ocr_text=ocr_text,
        analiz=analiz
    )

if __name__ == "__main__":
    app.run(debug=True, port=5001)