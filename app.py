from flask import Flask, render_template, request, redirect, url_for, session
import os
import re
import cv2
import sqlite3
import pytesseract
import uuid
from openai import OpenAI

if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:
    pytesseract.pytesseract.tesseract_cmd = "tesseract"     

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
        user_id INTEGER,
        tarih TEXT,
        toplam REAL,
        kategori TEXT,
        magaza TEXT,
        kdv REAL DEFAULT 0,
        kdv_orani TEXT,
        dosya_adi TEXT,
        eklenme_tarihi TEXT,
        ai_yorum TEXT,
        ocr_text TEXT,
        duzeltilmis INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        sifre TEXT NOT NULL
    )
    """)

    # Eski veritabanında kolonlar yoksa ekler
    for kolon in [
        "ai_yorum TEXT",
        "ocr_text TEXT",
        "kdv REAL DEFAULT 0",
        "kdv_orani TEXT",
        "dosya_adi TEXT",
        "eklenme_tarihi TEXT"
    ]:
        try:
            cursor.execute(f"ALTER TABLE fisler ADD COLUMN {kolon}")
        except:
            pass

    conn.commit()
    conn.close()

init_db()


def temizle_text(ocr_text):
    text = ocr_text.lower()
    text = text.replace("i̇", "i")
    text = text.replace("ı", "i")
    text = text.replace("ş", "s")
    text = text.replace("ğ", "g")
    text = text.replace("ü", "u")
    text = text.replace("ö", "o")
    text = text.replace("ç", "c")
    return text


def kategori_bul(ocr_text):
    text = temizle_text(ocr_text)

    if "a101" in text or "migros" in text or "bim" in text or "sok" in text:
        return "Market"

    elif "starbucks" in text or "burger" in text or "mcdonald" in text or "popeyes" in text or "kfc" in text or "pizza" in text:
        return "Yeme İçme"

    elif "teknosa" in text or "vatan" in text or "media markt" in text:
        return "Teknoloji"

    return "Diğer"


def magaza_bul(ocr_text):
    text = temizle_text(ocr_text)

    if "a101" in text:
        return "A101"

    elif "migros" in text:
        return "Migros"

    elif "bim" in text:
        return "BİM"

    elif "sok" in text:
        return "ŞOK"

    elif "starbucks" in text:
        return "Starbucks"

    elif "teknosa" in text:
        return "Teknosa"
    
    if "popeyes" in text:
        return "Popeyes"
    
    if "kfc" in text:
        return "KFC"
    
    if "pizza" in text:
        return "Pizza Hut"
    


    return "Bilinmiyor"

def resmi_iyilestir(dosya_yolu):

    img = cv2.imread(dosya_yolu)

    if img is None:
        raise Exception("Resim okunamadı")

    gri = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

    return gri

# -------------------------
# OCR ANALİZ
# -------------------------
def fis_bilgilerini_cek(ocr_text):

    tarih = "Bulunamadı"
    toplam = "Bulunamadı"
    kdv = 0.0
    kdv_orani = "Bulunamadı"

    tarih_match = re.search(r"\d{2}[./]\d{2}[./]\d{4}", ocr_text)

    if tarih_match:
        tarih = tarih_match.group()

    satirlar = ocr_text.splitlines()
    oranlar = []

    for satir in satirlar:

        temiz_satir = satir.strip()
        kucuk = temiz_satir.lower()

        # TOPLAM
        if "toplam" in kucuk and "topkdv" not in kucuk:

            temiz_toplam = temiz_satir.replace(" ", "")

            toplam_match = re.search(
                r"(\d{1,3}(?:\.\d{3})*,\d{2})",
                temiz_toplam
            )

            if toplam_match:
                toplam = toplam_match.group(1)

        # TOPKDV
        if "topkdv" in kucuk:

            temiz_kdv = temiz_satir.replace(" ", "")

            kdv_match = re.search(
                r"(\d{1,3}(?:\.\d{3})*,\d{2})",
                temiz_kdv
            )

            if kdv_match:

                try:
                    kdv = float(
                        kdv_match.group(1)
                        .replace(".", "")
                        .replace(",", ".")
                    )
                except:
                    pass

        # KDV ORANI
        oran_match = re.findall(r"%\d{1,2}", temiz_satir)

        for oran in oran_match:
            oranlar.append(oran)

    if oranlar:
        kdv_orani = ", ".join(sorted(set(oranlar)))

    return {
        "tarih": tarih,
        "toplam": toplam,
        "kdv": round(kdv, 2),
        "kdv_orani": kdv_orani
    }
   

def ai_fis_analizi(ocr_text):

    prompt = f"""
Sen bir finansal harcama analiz uzmanısın.

Aşağıdaki OCR ile okunmuş fiş metnini analiz et.

Analiz sırasında:

- Fişteki ürünleri incele.
- Harcama alışkanlığını yorumla.
- Gereksiz veya lüks harcamaları belirt.
- Tasarruf önerileri ver.
- OCR kaynaklı olabilecek hataları tespit et.
- Fiş toplamı ile ürün fiyatlarını karşılaştır.
- Mantıksız görünen fiyatları özellikle belirt.
- Büyük ihtimalle yanlış okunmuş ürün veya tutarlar varsa tahmini doğru değeri yaz.
- Kullanıcıya 100 üzerinden harcama puanı ver.

Cevabı aşağıdaki formatta oluştur:

HARCAMA_OZETI:
...

DIKKAT_CEKENLER:
- ...
- ...
- ...

OCR_HATALARI:
- ...
- ...
- ...

TASARRUF_ONERISI:
...

PUAN:
...

GENEL_DEGERLENDIRME:
...

Fiş Metni:
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

@app.route("/login", methods=["GET", "POST"])
def login():

    hata = None

    if request.method == "POST":

        email = request.form["email"]
        sifre = request.form["sifre"]

        try:
            conn = sqlite3.connect("fisler.db")
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, ad, sifre
                FROM users
                WHERE email=?
            """, (email,))

            user = cursor.fetchone()

            conn.close()

            if user is None:
                hata = "Bu e-posta ile kayıtlı hesap bulunamadı."

            elif user[2] != sifre:
                hata = "Şifre yanlış."

            else:
                session["user_id"] = user[0]
                session["user_name"] = user[1]

                return redirect("/dashboard")

        except:
            hata = "Giriş yapılırken bir hata oluştu."

    return render_template("login.html", hata=hata)

@app.route("/register", methods=["GET", "POST"])
def register():

    hata = None

    if request.method == "POST":

        try:
            ad = request.form["ad"]
            email = request.form["email"]
            sifre = request.form["sifre"]
            sifre_tekrar = request.form["sifre_tekrar"]

            if sifre != sifre_tekrar:
                hata = "Şifreler eşleşmiyor."

            elif len(ad.strip()) < 3:
                hata = "Ad Soyad en az 3 karakter olmalıdır."

            elif len(sifre) < 6:
                hata = "Şifre en az 6 karakter olmalıdır."

            elif not any(char.isdigit() for char in sifre):
                hata = "Şifre en az 1 rakam içermelidir."

            elif not any(char.isalpha() for char in sifre):
                hata = "Şifre en az 1 harf içermelidir."

            else:
                conn = sqlite3.connect("fisler.db")
                cursor = conn.cursor()

                cursor.execute("""
                CREATE TABLE IF NOT EXISTS users(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ad TEXT,
                    email TEXT UNIQUE,
                    sifre TEXT
                )
                """)

                cursor.execute("""
                INSERT INTO users(ad, email, sifre)
                VALUES(?, ?, ?)
                """, (ad, email, sifre))

                conn.commit()
                conn.close()

                return redirect("/login")

        except sqlite3.IntegrityError:
            hata = "Bu e-posta zaten kayıtlı."

        except Exception as e:
            hata = "Kayıt sırasında bir hata oluştu."

    return render_template("register.html", hata=hata)

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    # kdv kolonu yoksa ekler
    try:
        cursor.execute("ALTER TABLE fisler ADD COLUMN kdv REAL DEFAULT 0")
        conn.commit()
    except:
        pass

    cursor.execute("SELECT COUNT(*) FROM fisler WHERE user_id=?", (session["user_id"],))
    toplam_fis = cursor.fetchone()[0]

    cursor.execute("SELECT toplam FROM fisler WHERE user_id=?", (session["user_id"],))
    toplamlar = cursor.fetchall()

    toplam_harcama = 0
    for t in toplamlar:
        try:
            toplam_harcama += float(str(t[0]).replace(",", "."))
        except:
            pass

    cursor.execute("SELECT kdv FROM fisler WHERE user_id=?", (session["user_id"],))
    kdvler = cursor.fetchall()

    toplam_kdv = 0
    for k in kdvler:
        try:
            toplam_kdv += float(str(k[0]).replace(",", "."))
        except:
            pass

    cursor.execute("SELECT COUNT(*) FROM fisler WHERE user_id=? AND kategori LIKE ?", (session["user_id"], "%Market%"))
    market = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM fisler WHERE user_id=? AND kategori LIKE ?", (session["user_id"], "%Yeme%"))
    yeme_icme = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM fisler WHERE user_id=? AND kategori LIKE ?", (session["user_id"], "%Teknoloji%"))
    teknoloji = cursor.fetchone()[0]

    conn.close()

    return render_template(
    "dashboard.html",
    toplam_fis=toplam_fis,
    toplam_harcama=round(toplam_harcama, 2),
    toplam_kdv=round(toplam_kdv, 2),
    market=market,
    yeme_icme=yeme_icme,
    teknoloji=teknoloji,
    analiz=session.get("analiz"),
    ocr_text=session.get("ocr_text"),
    ai_yorum=session.get("ai_yorum"),
    hata=session.pop("hata",None)
)

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if request.method == "POST":

        print("FILES:", request.files)

        file = request.files.get("receipt")

        if file is None or file.filename == "":
            print("DOSYA SECILMEDI")
            return redirect(url_for("dashboard"))

        print("FILENAME:", file.filename)

        os.makedirs("uploads", exist_ok=True)

        dosya_adi = str(uuid.uuid4()) + ".png"
        file_path = os.path.join("uploads", dosya_adi)

        file.save(file_path)

        print("KAYDEDILDI:", file_path)

        try:
            temiz_resim = resmi_iyilestir(file_path)

            ocr_text = pytesseract.image_to_string(
                temiz_resim,
                lang="tur+eng",
                config="--oem 3 --psm 6"
)

            print("OCR SONUCU:")
            print(ocr_text)

            ai_yorum = ai_fis_analizi(ocr_text)
            
            ai_yorum = ai_yorum.replace(
                "HARCAMA_OZETI:",
                '<span class="ai-title">📊 Harcama Özeti</span>'
            )

            ai_yorum = ai_yorum.replace(
                "DIKKAT_CEKENLER:",
                '<span class="ai-title">⚠️ Dikkat Çeken Noktalar</span>'
            )

            ai_yorum = ai_yorum.replace(
                "OCR_HATALARI:",
                '<span class="ai-title">🔍 OCR Hata Kontrolü</span>'
            )

            ai_yorum = ai_yorum.replace(
                "TASARRUF_ONERISI:",
                '<span class="ai-title">💰 Tasarruf Önerisi</span>'
            )

            ai_yorum = ai_yorum.replace(
                "GENEL_DEGERLENDIRME:",
                '<span class="ai-title">⭐ Genel Değerlendirme</span>'
            )

            ai_yorum = ai_yorum.replace(
                "PUAN:",
                '<span class="ai-title">🏆 Harcama Puanı</span>'
            )
            session["ai_yorum"] = ai_yorum

            print("AI YORUM:")
            print(ai_yorum)

            analiz = fis_bilgilerini_cek(ocr_text)

            kategori = kategori_bul(ocr_text)
            magaza = magaza_bul(ocr_text)

            analiz["kategori"] = kategori
            analiz["magaza"] = magaza

            tarih = analiz.get("tarih", "")
            toplam = analiz.get("toplam", 0)
            kdv = analiz.get("kdv", 0)

            kdv_orani = analiz.get("kdv_orani", "Bulunamadı")

            print("ANALİZ:", analiz)
            print("KDV:", kdv)

            session["ocr_text"] = ocr_text
            session["analiz"] = analiz

            conn = sqlite3.connect("fisler.db")
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO fisler(user_id, magaza, tarih, toplam, kategori, kdv, kdv_orani, ai_yorum, ocr_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
               session.get("user_id"),
               magaza,
               tarih,
               toplam,
               kategori,
               kdv,
               kdv_orani,
               ai_yorum,
               ocr_text
))

            conn.commit()
            conn.close()

            print("VERITABANINA KAYDEDILDI")

            return redirect(url_for("dashboard"))

        except Exception as e:
            print("HATA:")
            print(e)
            session["hata"] = str(e)
            return redirect(url_for("dashboard"))

    return redirect(url_for("dashboard"))

# -------------------------
# FİŞ GEÇMİŞİ
# -------------------------

@app.route("/receipts")
def receipts():

    user_id = session.get("user_id")

    if not user_id:
        return redirect("/login")

    magaza = request.args.get("magaza", "")
    kategori = request.args.get("kategori", "")
    tarih = request.args.get("tarih", "")

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    sql = """
    SELECT *
    FROM fisler
    WHERE user_id=?
    """

    params = [user_id]

    if magaza:
        sql += " AND magaza LIKE ?"
        params.append(f"%{magaza}%")

    if kategori:
        sql += " AND kategori=?"
        params.append(kategori)

    if tarih:
        sql += " AND tarih=?"
        params.append(tarih)

    sql += " ORDER BY id DESC"

    cursor.execute(sql, tuple(params))

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

    user_id = session.get("user_id")

    if not user_id:
        return redirect("/login")

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    # Toplam fiş sayısı
    cursor.execute("""
        SELECT COUNT(*)
        FROM fisler
        WHERE user_id=?
    """, (user_id,))
    toplam_fis = cursor.fetchone()[0]

    # Toplam KDV
    cursor.execute("""
        SELECT SUM(kdv)
        FROM fisler
        WHERE user_id=?
    """, (user_id,))

    toplam_kdv = cursor.fetchone()[0]

    if toplam_kdv is None:
        toplam_kdv = 0

    # Tarih ve toplam bilgileri
    cursor.execute("""
        SELECT tarih, toplam
        FROM fisler
        WHERE user_id=?
    """, (user_id,))

    veriler = cursor.fetchall()

    toplam_harcama = 0
    en_buyuk = 0

    aylar = {
        "01": 0,
        "02": 0,
        "03": 0,
        "04": 0,
        "05": 0,
        "06": 0,
        "07": 0,
        "08": 0,
        "09": 0,
        "10": 0,
        "11": 0,
        "12": 0
    }

    ay_isimleri = {
        "01": "Ocak",
        "02": "Şubat",
        "03": "Mart",
        "04": "Nisan",
        "05": "Mayıs",
        "06": "Haziran",
        "07": "Temmuz",
        "08": "Ağustos",
        "09": "Eylül",
        "10": "Ekim",
        "11": "Kasım",
        "12": "Aralık"
    }

    # Harcama hesapları
    for tarih, toplam in veriler:

        try:
            tutar = float(str(toplam).replace(",", "."))

            toplam_harcama += tutar

            if tutar > en_buyuk:
                en_buyuk = tutar

            temiz_tarih = str(tarih).replace(".", "/")

            if len(temiz_tarih) >= 10:
                ay = temiz_tarih[3:5]

                if ay in aylar:
                    aylar[ay] += tutar

        except:
            pass

    # Ortalama fiş tutarı
    ortalama = round(
        toplam_harcama / toplam_fis,
        2
    ) if toplam_fis > 0 else 0

    # Kategori dağılımı (Sadece giriş yapan kullanıcı)
    cursor.execute("""
        SELECT kategori, COUNT(*)
        FROM fisler
        WHERE user_id=?
        GROUP BY kategori
    """, (user_id,))

    kategori_verileri = cursor.fetchall()

    kategori_etiketleri = []
    kategori_sayilari = []

    for kategori in kategori_verileri:
        kategori_etiketleri.append(kategori[0])
        kategori_sayilari.append(kategori[1])
            # En çok harcanan kategori

    cursor.execute("""
        SELECT kategori, SUM(
            CAST(REPLACE(toplam, ',', '.') AS REAL)
        ) as toplam_tutar
        FROM fisler
        WHERE user_id=?
        GROUP BY kategori
        ORDER BY toplam_tutar DESC
        LIMIT 1
    """, (user_id,))

    en_kategori = cursor.fetchone()

    if en_kategori:
        kategori_adi = en_kategori[0]
        kategori_tutari = round(en_kategori[1], 2)
    else:
        kategori_adi = "Yok"
        kategori_tutari = 0

        

    # En çok gidilen mağazalar (Sadece giriş yapan kullanıcı)
    cursor.execute("""
        SELECT magaza, COUNT(*)
        FROM fisler
        WHERE user_id=?
        GROUP BY magaza
        ORDER BY COUNT(*) DESC
        LIMIT 5
    """, (user_id,))

    magazalar = cursor.fetchall()

    yorumlar = []

    # En çok kategori
    if kategori_adi == "Market":
        yorumlar.append(
            "Harcamalarınızın büyük kısmı market alışverişlerinden oluşuyor."
        )

    elif kategori_adi == "Teknoloji":
        yorumlar.append(
            "Teknoloji kategorisi bu dönemde en yüksek harcama kaleminiz."
        )

    elif kategori_adi == "Yeme İçme":
        yorumlar.append(
            "Yeme içme harcamalarınız dikkat çekici seviyede."
        )

    # En çok mağaza
    if len(magazalar) > 0:
        yorumlar.append(
            f"En sık alışveriş yaptığınız mağaza {magazalar[0][0]}."
        )

    # Ortalama fiş
    if ortalama > 300:
        yorumlar.append(
            "Ortalama fiş tutarınız yüksek seviyede."
        )

    elif ortalama < 100:
        yorumlar.append(
            "Ortalama fiş tutarınız kontrollü görünüyor."
        )

            # Tasarruf fırsatı

    tasarruf_tutari = 0
    tasarruf_mesaji = "Tasarruf önerisi oluşturulamadı."

    if kategori_adi == "Market":

        tasarruf_tutari = round(
            kategori_tutari * 0.05,
            2
        )

        tasarruf_mesaji = (
            f"Market harcamalarınızı %5 azaltırsanız yaklaşık "
            f"{tasarruf_tutari} TL tasarruf edebilirsiniz."
        )

    elif kategori_adi == "Yeme İçme":

        tasarruf_tutari = round(
            kategori_tutari * 0.10,
            2
        )

        tasarruf_mesaji = (
            f"Yeme içme harcamalarınızı %10 azaltırsanız yaklaşık "
            f"{tasarruf_tutari} TL tasarruf edebilirsiniz."
        )

    elif kategori_adi == "Teknoloji":

        tasarruf_tutari = round(
            kategori_tutari * 0.15,
            2
        )

        tasarruf_mesaji = (
            f"Teknoloji alışverişlerinde daha planlı davranarak yaklaşık "
            f"{tasarruf_tutari} TL tasarruf edebilirsiniz."
        )
     
    # Aylık harcamalar
    ay_etiketleri = []
    ay_tutarlari = []

    for ay_no in aylar:
        if aylar[ay_no] > 0:
            ay_etiketleri.append(ay_isimleri[ay_no])
            ay_tutarlari.append(round(aylar[ay_no], 2))


    conn.close()

    return render_template(
        "reports.html",
        toplam_fis=toplam_fis,
        toplam_harcama=round(toplam_harcama, 2),
        ortalama=ortalama,
        en_buyuk=round(en_buyuk, 2),
        toplam_kdv=round(toplam_kdv, 2),
        kategori_etiketleri=kategori_etiketleri,
        kategori_sayilari=kategori_sayilari,
        magazalar=magazalar,
        ay_etiketleri=ay_etiketleri,
        ay_tutarlari=ay_tutarlari,
        kategori_adi=kategori_adi,
        kategori_tutari=kategori_tutari,
        yorumlar=yorumlar,
        tasarruf_tutari=tasarruf_tutari,
        tasarruf_mesaji=tasarruf_mesaji
        
    )







@app.route("/uye_profil")
def uye_profil():

    user_id = session.get("user_id")

    if not user_id:
        return redirect("/login")

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ad, email
        FROM users
        WHERE id=?
    """, (user_id,))

    user = cursor.fetchone()

    conn.close()

    if user is None:
        return redirect("/dashboard")

    return render_template(
        "uye_profil.html",
        user={
            "name": user[0],
            "email": user[1]
        }
    )

    
@app.route("/profil_guncelle", methods=["POST"])
def profil_guncelle():

    if "user_id" not in session:
        return redirect("/login")

    email = request.form["email"]

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE users
    SET email=?
    WHERE id=?
    """, (
        email,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect("/uye_profil")

@app.route("/sifre_degistir", methods=["POST"])
def sifre_degistir():

    if "user_id" not in session:
        return redirect("/login")

    eski = request.form["old_password"]
    yeni = request.form["new_password"]

    conn = sqlite3.connect("fisler.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT sifre
    FROM users
    WHERE id=?
    """, (session["user_id"],))

    mevcut_sifre = cursor.fetchone()[0]

    if mevcut_sifre != eski:
        conn.close()
        return "Eski şifre yanlış"

    cursor.execute("""
    UPDATE users
    SET sifre=?
    WHERE id=?
    """, (
        yeni,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect("/uye_profil")







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