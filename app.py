from flask import Flask, render_template, request
import os
import re
import cv2
import sqlite3
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)

# -------------------------
# VERİTABANI
# -------------------------

def init_db():
    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fisler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT,
    toplam REAL,
    kategori TEXT,
    magaza TEXT,
    kdv REAL,
    dosya_adi TEXT,
    eklenme_tarihi TEXT
)
""")

    conn.commit()
    conn.close()

init_db()

# -------------------------
# KATEGORİ BUL
# -------------------------

def kategori_bul(ocr_text):

    text = ocr_text.lower()

    if "a101" in text:
        return "Market"

    elif "migros" in text:
        return "Market"

    elif "bim" in text:
        return "Market"

    elif "şok" in text:
        return "Market"

    elif "starbucks" in text:
        return "Yeme İçme"

    elif "burger king" in text:
        return "Yeme İçme"

    elif "mcdonald" in text:
        return "Yeme İçme"

    elif "teknosa" in text:
        return "Teknoloji"

    elif "vatan" in text:
        return "Teknoloji"

    elif "media markt" in text:
        return "Teknoloji"

    return "Diğer"

def magaza_bul(ocr_text):

    text = ocr_text.lower()

    if "a101" in text:
        return "A101"

    elif "migros" in text:
        return "Migros"

    elif "bim" in text:
        return "BİM"

    elif "şok" in text:
        return "ŞOK"

    elif "starbucks" in text:
        return "Starbucks"

    elif "teknosa" in text:
        return "Teknosa"

    return "Bilinmiyor"

# -------------------------
# RESİM İYİLEŞTİRME
# -------------------------

def resmi_iyilestir(dosya_yolu):

    img = cv2.imread(dosya_yolu)

    gri = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    gri = cv2.resize(
        gri,
        None,
        fx=2,
        fy=2
    )

    gri = cv2.GaussianBlur(
        gri,
        (3, 3),
        0
    )

    _, esik = cv2.threshold(
        gri,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return esik

# -------------------------
# OCR ANALİZ
# -------------------------

def fis_bilgilerini_cek(ocr_text):

    tarih = re.search(
        r"\d{2}[./-]\d{2}[./-]\d{4}",
        ocr_text
    )

    tutarlar = re.findall(
        r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}",
        ocr_text
    )

    toplam = "Bulunamadı"

    if tutarlar:
        toplam = tutarlar[-1]

    return {
        "tarih": tarih.group() if tarih else "Bulunamadı",
        "toplam": toplam
    }

# -------------------------
# SAYFALAR
# -------------------------

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

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM fisler")
    toplam_fis = cursor.fetchone()[0]

    cursor.execute("SELECT toplam FROM fisler")
    tutarlar = cursor.fetchall()

    toplam_harcama = 0

    for t in tutarlar:
        try:
            toplam_harcama += float(str(t[0]).replace(",", "."))
        except:
            pass

    cursor.execute(
        "SELECT COUNT(*) FROM fisler WHERE kategori='Market'"
    )
    market = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM fisler WHERE kategori='Yeme İçme'"
    )
    yeme_icme = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM fisler WHERE kategori='Teknoloji'"
    )
    teknoloji = cursor.fetchone()[0]

    conn.close()

    kategori_etiketleri = [
        "Market",
        "Yeme İçme",
        "Teknoloji"
    ]

    kategori_sayilari = [
        market,
        yeme_icme,
        teknoloji
    ]

    return render_template(
        "dashboard.html",
        toplam_fis=toplam_fis,
        toplam_harcama=round(toplam_harcama, 2),
        market=market,
        yeme_icme=yeme_icme,
        teknoloji=teknoloji,
        kategori_etiketleri=kategori_etiketleri,
        kategori_sayilari=kategori_sayilari
    )

# -------------------------
# FİŞ YÜKLE
# -------------------------

@app.route("/upload", methods=["GET", "POST"])
def upload():

    message = None
    ocr_text = None
    analiz = None

    if request.method == "POST":

        file = request.files.get("receipt")

        if file and file.filename != "":

            os.makedirs(
                "uploads",
                exist_ok=True
            )

            file_path = os.path.join(
                "uploads",
                file.filename
            )

            file.save(file_path)

            temiz_resim = resmi_iyilestir(file_path)

            ocr_text = pytesseract.image_to_string(
                temiz_resim,
                lang="eng",
                config="--oem 3 --psm 6"
            )

            analiz = fis_bilgilerini_cek(ocr_text)

            kategori = kategori_bul(ocr_text)

            analiz["magaza"] = magaza_bul(ocr_text)

            analiz["kategori"] = kategori

            conn = sqlite3.connect("fisler.db")
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO fisler
                (tarih, toplam, kategori, magaza)
                VALUES (?, ?, ?, ?)
                """,
                (
                    analiz["tarih"],
                    analiz["toplam"],
                    analiz["kategori"],
                    analiz["magaza"]
                )
            )

            conn.commit()
            conn.close()

            message = "Fiş başarıyla yüklendi ve analiz edildi!"

    return render_template(
        "upload.html",
        message=message,
        ocr_text=ocr_text,
        analiz=analiz
    )

# -------------------------
# FİŞ GEÇMİŞİ
# -------------------------

@app.route("/receipts")
def receipts():

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM fisler ORDER BY id DESC"
    )

    fisler = cursor.fetchall()

    conn.close()

    return render_template(
        "receipts.html",
        fisler=fisler
    )

# -------------------------
# ÇALIŞTIR
# -------------------------

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5001
    )