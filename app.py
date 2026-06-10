from flask import Flask, render_template, request, redirect, url_for, session
import os
import re
import cv2
import sqlite3
import pytesseract
import uuid
from openai import OpenAI

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

api_key = os.getenv("OPENAI_API_KEY")

print("DEBUG KEY:", api_key)

from openai import OpenAI
client = OpenAI(api_key=api_key)
app = Flask(__name__)
app.secret_key = "fisai123"

load_dotenv()
client = OpenAI(
    api_key= os.getenv("OPENAI_API_KEY")
)




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
        eklenme_tarihi TEXT,
        duzeltilmis INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

init_db()


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



def resmi_iyilestir(dosya_yolu):

    print("Dosya yolu:", dosya_yolu)

    img = cv2.imread(dosya_yolu)

    if img is None:
        raise Exception(f"Resim okunamadı -> {dosya_yolu}")

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

    tarih = "Bulunamadı"
    toplam = "Bulunamadı"

    tarih_match = re.search(
        r"\d{2}[./]\d{2}[./]\d{4}",
        ocr_text
    )

    if tarih_match:
        tarih = tarih_match.group()

    tutarlar = re.findall(
        r"\d+[.,]\d{2}",
        ocr_text
    )

    if tutarlar:
        try:
            toplam = max(
                tutarlar,
                key=lambda x: float(
                    x.replace(",", ".")
                )
            )
        except:
            toplam = tutarlar[-1]

    return {
        "tarih": tarih,
        "toplam": toplam
    }

def ai_fis_analizi(ocr_text):

    prompt = f"""
Aşağıdaki OCR ile okunmuş fiş metnini analiz et.

Cevabı markdown kullanmadan, sadece şu formatta ver:

Mağaza: ...
Tarih: ...
Toplam tutar: ...
Kategori: ...
Harcama yorumu: ...

Fiş metni:
{ocr_text}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return response.output_text
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
    kategori_sayilari=kategori_sayilari,

    ocr_text=session.get("ocr_text"),
    analiz=session.get("analiz"),
    ai_yorum=session.get("ai_yorum")
)

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if request.method == "POST":

        print("FILES:", request.files)

        file = request.files.get("receipt")

        if file is None:
            print("DOSYA GELMEDI")
            return redirect(url_for("dashboard"))

        print("FILENAME:", file.filename)

        if file.filename == "":
            print("DOSYA SECILMEDI")
            return redirect(url_for("dashboard"))

        os.makedirs(
            "uploads",
            exist_ok=True
        )

        dosya_adi = str(uuid.uuid4()) + ".png"

        file_path = os.path.join(
            "uploads",
            dosya_adi
        )

        file.save(file_path)

        print("KAYDEDILDI:", file_path)

        try:

            temiz_resim = resmi_iyilestir(file_path)

            ocr_text = pytesseract.image_to_string(
                temiz_resim,
                lang="eng",
                config="--oem 3 --psm 6"
            )

            print("OCR SONUCU:")
            print(ocr_text)

            ai_yorum = ai_fis_analizi(ocr_text)

            session["ai_yorum"] = ai_yorum

            print("AI YORUM:")
            print(ai_yorum)

            analiz = fis_bilgilerini_cek(ocr_text)

            kategori = kategori_bul(ocr_text)

            analiz["magaza"] = magaza_bul(ocr_text)
            analiz["kategori"] = kategori

            # DASHBOARD'DA GÖSTERMEK İÇİN
            session["ocr_text"] = ocr_text
            session["analiz"] = analiz

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

            print("VERITABANINA KAYDEDILDI")

        except Exception as e:

            print("HATA:")
            print(e)

        return redirect(url_for("dashboard"))

    return redirect(url_for("dashboard"))

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

@app.route("/delete/<int:id>")
def delete_receipt(id):

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM fisler WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("receipts"))


@app.route("/delete_all")
def delete_all():

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM fisler")

    conn.commit()
    conn.close()

    return redirect(url_for("receipts"))


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_receipt(id):

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    if request.method == "POST":

        tarih = request.form["tarih"]
        toplam = request.form["toplam"]
        magaza = request.form["magaza"]
        kategori = request.form["kategori"]

        cursor.execute("""
            UPDATE fisler
            SET tarih=?, toplam=?, magaza=?, kategori=?, duzeltilmis=1
            WHERE id=?
        """, (tarih, toplam, magaza, kategori, id))

        conn.commit()
        conn.close()

        return redirect(url_for("receipts"))

    cursor.execute("SELECT * FROM fisler WHERE id=?", (id,))
    fis = cursor.fetchone()

    conn.close()

    return render_template("edit.html", fis=fis)

@app.route("/reports")
def reports():

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    # Toplam fiş
    cursor.execute("SELECT COUNT(*) FROM fisler")
    toplam_fis = cursor.fetchone()[0]

    # Toplam harcama
    cursor.execute("SELECT toplam FROM fisler")
    tutarlar = cursor.fetchall()

    toplam_harcama = 0

    for t in tutarlar:
        try:
            toplam_harcama += float(str(t[0]).replace(",", "."))
        except:
            pass

    # Ortalama fiş
    ortalama = round(
        toplam_harcama / toplam_fis,
        2
    ) if toplam_fis > 0 else 0

    # En büyük fiş
    en_buyuk = 0

    for t in tutarlar:
        try:
            deger = float(str(t[0]).replace(",", "."))
            if deger > en_buyuk:
                en_buyuk = deger
        except:
            pass

    # Kategoriler
    cursor.execute("""
        SELECT kategori, COUNT(*)
        FROM fisler
        GROUP BY kategori
    """)

    kategori_verileri = cursor.fetchall()

    kategori_etiketleri = []
    kategori_sayilari = []

    for kategori in kategori_verileri:
        kategori_etiketleri.append(kategori[0])
        kategori_sayilari.append(kategori[1])

    # Mağaza sıralaması
    cursor.execute("""
        SELECT magaza, COUNT(*)
        FROM fisler
        GROUP BY magaza
        ORDER BY COUNT(*) DESC
        LIMIT 5
    """)

    magazalar = cursor.fetchall()

    conn.close()

    return render_template(
        "reports.html",
        toplam_fis=toplam_fis,
        toplam_harcama=round(toplam_harcama, 2),
        ortalama=ortalama,
        en_buyuk=en_buyuk,
        kategori_etiketleri=kategori_etiketleri,
        kategori_sayilari=kategori_sayilari,
        magazalar=magazalar
    )


@app.route("/clear_dashboard")
def clear_dashboard():

    session.pop("ocr_text", None)
    session.pop("analiz", None)
    session.pop("ai_yorum", None)

    return redirect(url_for("dashboard"))


# -------------------------
# ÇALIŞTIR
# -------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001))
    )