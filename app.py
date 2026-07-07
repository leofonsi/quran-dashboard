from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import io
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except Exception:
    arabic_reshaper = None
    get_display = None
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quran_dashboard.db"

app = FastAPI(title="تطبيق متابعة حفظ القرآن")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_code TEXT UNIQUE,
        full_name TEXT NOT NULL,
        age INTEGER,
        level TEXT,
        phone_guardian TEXT,
        created_at TEXT DEFAULT CURRENT_DATE
    )
    """)
    # إضافة عمود رمز الطالب تلقائياً إذا كانت قاعدة البيانات قديمة
    cols = [row[1] for row in cur.execute("PRAGMA table_info(students)").fetchall()]
    if "student_code" not in cols:
        cur.execute("ALTER TABLE students ADD COLUMN student_code TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        eval_date TEXT NOT NULL,
        surah TEXT NOT NULL,
        ayat_from TEXT,
        ayat_to TEXT,
        pages REAL DEFAULT 0,
        mistakes INTEGER DEFAULT 0,
        attendance TEXT DEFAULT 'حاضر',
        revision TEXT DEFAULT 'نعم',
        note REAL DEFAULT 0,
        remark TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )
    """)
    conn.commit()

    count = cur.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    if count == 0:
        demo_students = [
            ("QH-001", "أحمد العلمي", 12, "مبتدئ", "0600000001"),
            ("QH-002", "يوسف الإدريسي", 14, "متوسط", "0600000002"),
            ("QH-003", "عمر السعيدي", 11, "متقدم", "0600000003"),
        ]
        cur.executemany("INSERT INTO students(student_code, full_name, age, level, phone_guardian) VALUES (?, ?, ?, ?, ?)", demo_students)
        demo_evals = [
            (1, str(date.today()), "البقرة", "1", "20", 2, 3, "حاضر", "نعم", 16, "تقدم جيد"),
            (2, str(date.today()), "يس", "1", "15", 1.5, 5, "حاضر", "نعم", 13, "يحتاج إلى مراجعة"),
            (3, str(date.today()), "الملك", "1", "30", 3, 1, "حاضر", "نعم", 18, "ممتاز"),
        ]
        cur.executemany("""
        INSERT INTO evaluations(student_id, eval_date, surah, ayat_from, ayat_to, pages, mistakes, attendance, revision, note, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, demo_evals)
        conn.commit()

    # إنشاء رموز للطلاب القدامى الذين لا يتوفرون على رمز
    missing_codes = cur.execute("SELECT id FROM students WHERE student_code IS NULL OR student_code='' ORDER BY id").fetchall()
    for row in missing_codes:
        cur.execute("UPDATE students SET student_code=? WHERE id=?", (f"QH-{row[0]:03d}", row[0]))
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup_event():
    init_db()


def get_students():
    conn = db_conn()
    rows = conn.execute("SELECT * FROM students ORDER BY student_code ASC, id ASC").fetchall()
    conn.close()
    return rows


def get_evaluations(limit=100):
    conn = db_conn()
    rows = conn.execute("""
        SELECT e.*, s.full_name, s.student_code
        FROM evaluations e
        JOIN students s ON s.id = e.student_id
        ORDER BY e.eval_date DESC, e.id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def performance_label(note):
    if note >= 17:
        return "ممتاز"
    if note >= 14:
        return "جيد"
    if note >= 10:
        return "متوسط"
    return "ضعيف"


def ar(text):
    """تهيئة النص العربي للظهور بشكل صحيح داخل PDF والرسوم."""
    text = "" if text is None else str(text)
    if arabic_reshaper and get_display:
        return get_display(arabic_reshaper.reshape(text))
    return text

SURAH_NAMES = [
    "الفاتحة", "البقرة", "آل عمران", "النساء", "المائدة", "الأنعام", "الأعراف", "الأنفال", "التوبة", "يونس",
    "هود", "يوسف", "الرعد", "إبراهيم", "الحجر", "النحل", "الإسراء", "الكهف", "مريم", "طه",
    "الأنبياء", "الحج", "المؤمنون", "النور", "الفرقان", "الشعراء", "النمل", "القصص", "العنكبوت", "الروم",
    "لقمان", "السجدة", "الأحزاب", "سبأ", "فاطر", "يس", "الصافات", "ص", "الزمر", "غافر",
    "فصلت", "الشورى", "الزخرف", "الدخان", "الجاثية", "الأحقاف", "محمد", "الفتح", "الحجرات", "ق",
    "الذاريات", "الطور", "النجم", "القمر", "الرحمن", "الواقعة", "الحديد", "المجادلة", "الحشر", "الممتحنة",
    "الصف", "الجمعة", "المنافقون", "التغابن", "الطلاق", "التحريم", "الملك", "القلم", "الحاقة", "المعارج",
    "نوح", "الجن", "المزمل", "المدثر", "القيامة", "الإنسان", "المرسلات", "النبأ", "النازعات", "عبس",
    "التكوير", "الانفطار", "المطففين", "الانشقاق", "البروج", "الطارق", "الأعلى", "الغاشية", "الفجر", "البلد",
    "الشمس", "الليل", "الضحى", "الشرح", "التين", "العلق", "القدر", "البينة", "الزلزلة", "العاديات",
    "القارعة", "التكاثر", "العصر", "الهمزة", "الفيل", "قريش", "الماعون", "الكوثر", "الكافرون", "النصر",
    "المسد", "الإخلاص", "الفلق", "الناس"
]

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    conn = db_conn()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    total_evals = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    avg_note = conn.execute("SELECT ROUND(AVG(note), 2) FROM evaluations").fetchone()[0] or 0
    attendance = conn.execute("SELECT COUNT(*) FROM evaluations WHERE attendance IN ('حاضر','Present')").fetchone()[0]
    attendance_rate = round((attendance / total_evals * 100), 2) if total_evals else 0

    top_students = conn.execute("""
        SELECT s.student_code, ROUND(AVG(e.note),2) AS avg_note, SUM(e.pages) AS total_pages
        FROM students s
        JOIN evaluations e ON e.student_id = s.id
        GROUP BY s.id
        ORDER BY avg_note DESC
        LIMIT 5
    """).fetchall()

    student_progress = conn.execute("""
        SELECT s.student_code, SUM(e.pages) AS pages, ROUND(AVG(e.note),2) AS avg_note, SUM(e.mistakes) AS mistakes
        FROM students s
        LEFT JOIN evaluations e ON e.student_id = s.id
        GROUP BY s.id
        ORDER BY pages DESC
    """).fetchall()
    conn.close()

    return templates.TemplateResponse(request, "index.html", {
        "total_students": total_students,
        "total_evals": total_evals,
        "avg_note": avg_note,
        "attendance_rate": attendance_rate,
        "top_students": top_students,
        "student_progress": student_progress,
    })


@app.get("/students", response_class=HTMLResponse)
def students_page(request: Request):
    return templates.TemplateResponse(request, "students.html", {"students": get_students()})


@app.post("/students/add")
def add_student(
    student_code: str = Form(""),
    full_name: str = Form(...),
    age: int = Form(0),
    level: str = Form("مبتدئ"),
    phone_guardian: str = Form("")
):
    conn = db_conn()
    cur = conn.cursor()
    if not student_code.strip():
        next_id = cur.execute("SELECT COALESCE(MAX(id),0)+1 FROM students").fetchone()[0]
        student_code = f"QH-{next_id:03d}"
    cur.execute("INSERT INTO students(student_code, full_name, age, level, phone_guardian) VALUES (?, ?, ?, ?, ?)",
                 (student_code.strip(), full_name, age, level, phone_guardian))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/students", status_code=303)


@app.post("/students/delete/{student_id}")
def delete_student(student_id: int):
    conn = db_conn()
    conn.execute("DELETE FROM evaluations WHERE student_id=?", (student_id,))
    conn.execute("DELETE FROM students WHERE id=?", (student_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/students", status_code=303)


@app.get("/evaluations", response_class=HTMLResponse)
def evaluations_page(request: Request):
    return templates.TemplateResponse(request, "evaluations.html", {
        "students": get_students(),
        "evaluations": get_evaluations(),
        "today": str(date.today()),
        "performance_label": performance_label,
        "surahs": SURAH_NAMES
    })


@app.post("/evaluations/add")
def add_evaluation(
    student_id: int = Form(...),
    eval_date: str = Form(...),
    surah: str = Form(...),
    ayat_from: str = Form(""),
    ayat_to: str = Form(""),
    pages: float = Form(0),
    mistakes: int = Form(0),
    attendance: str = Form("حاضر"),
    revision: str = Form("نعم"),
    note: float = Form(0),
    remark: str = Form("")
):
    conn = db_conn()
    conn.execute("""
        INSERT INTO evaluations(student_id, eval_date, surah, ayat_from, ayat_to, pages, mistakes, attendance, revision, note, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (student_id, eval_date, surah, ayat_from, ayat_to, pages, mistakes, attendance, revision, note, remark))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/evaluations", status_code=303)


@app.get("/report")
def report_redirect():
    return RedirectResponse(url="/report/pdf", status_code=303)


def get_arabic_font_path():
    """Find an Arabic-capable system font without shipping font files."""
    candidates = [
        BASE_DIR / "static" / "fonts" / "Cairo-Regular.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("C:/Windows/Fonts/seguiemj.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    # Matplotlib ships DejaVuSans; use it as final fallback.
    try:
        import matplotlib.font_manager as fm
        return fm.findfont("DejaVu Sans")
    except Exception:
        return None


def register_arabic_pdf_font():
    font_path = get_arabic_font_path()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("ArabicFont", font_path))
            return "ArabicFont"
        except Exception:
            pass
    return "Helvetica"


def rtl_text(text):
    """Convert Arabic text to a visual RTL form for PDF canvas/table rendering."""
    text = "" if text is None else str(text)
    if arabic_reshaper and get_display:
        return get_display(arabic_reshaper.reshape(text))
    return text


def draw_rtl(c, text, x, y, size=11, font="ArabicFont", color=colors.HexColor("#0f172a"), align="right"):
    c.setFillColor(color)
    c.setFont(font, size)
    shaped = rtl_text(text)
    if align == "center":
        c.drawCentredString(x, y, shaped)
    elif align == "left":
        c.drawString(x, y, shaped)
    else:
        c.drawRightString(x, y, shaped)


def make_chart_image(labels, values, kind="bar"):
    """Create a chart image with student codes only to avoid privacy issues and Arabic rendering problems."""
    img = io.BytesIO()
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    if kind == "line":
        ax.plot(labels, values, marker="o", linewidth=2)
    else:
        ax.bar(labels, values)
    ax.grid(axis="y" if kind == "bar" else "both", alpha=0.25)
    ax.tick_params(axis="x", rotation=25)
    ax.set_xlabel("رمز الطالب")
    ax.set_ylabel("النقطة/الصفحات")
    fig.tight_layout()
    fig.savefig(img, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    img.seek(0)
    return img


@app.get("/report/pdf")
def report_pdf():
    conn = db_conn()
    summary = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM students) AS total_students,
            (SELECT COUNT(*) FROM evaluations) AS total_evals,
            ROUND(COALESCE(AVG(note), 0), 2) AS avg_note,
            ROUND(COALESCE(SUM(pages), 0), 2) AS total_pages,
            COALESCE(SUM(mistakes), 0) AS total_mistakes,
            ROUND(CASE WHEN COUNT(*) = 0 THEN 0 ELSE SUM(CASE WHEN attendance IN ('حاضر','Present') THEN 1 ELSE 0 END) * 100.0 / COUNT(*) END, 2) AS attendance_rate
        FROM evaluations
    """).fetchone()
    progress = conn.execute("""
        SELECT s.full_name, s.student_code,
               ROUND(COALESCE(SUM(e.pages),0),2) AS pages,
               ROUND(COALESCE(AVG(e.note),0),2) AS avg_note,
               COALESCE(SUM(e.mistakes),0) AS mistakes,
               COUNT(e.id) AS total_evals
        FROM students s
        LEFT JOIN evaluations e ON e.student_id = s.id
        GROUP BY s.id
        ORDER BY avg_note DESC, pages DESC
    """).fetchall()
    last_evals = conn.execute("""
        SELECT e.eval_date, s.full_name, s.student_code, e.surah, e.pages, e.mistakes, e.note, e.attendance, e.remark
        FROM evaluations e
        JOIN students s ON s.id = e.student_id
        ORDER BY e.eval_date DESC, e.id DESC
        LIMIT 24
    """).fetchall()
    conn.close()

    buffer = io.BytesIO()
    font_name = register_arabic_pdf_font()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    green = colors.HexColor("#0f766e")
    dark = colors.HexColor("#0f172a")
    light = colors.HexColor("#f6fbf8")
    border = colors.HexColor("#dbe7e2")

    def footer(page_no):
        c.setStrokeColor(border)
        c.line(40, 35, width - 40, 35)
        draw_rtl(c, f"الصفحة {page_no}", width / 2, 20, 9, font_name, colors.HexColor("#64748b"), "center")

    # Page 1: cover and summary
    c.setFillColor(light)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    c.setStrokeColor(green)
    c.setLineWidth(2)
    c.rect(45, 55, width - 90, height - 110, stroke=1, fill=0)
    c.setFillColor(green)
    c.rect(45, height - 120, width - 90, 55, stroke=0, fill=1)
    draw_rtl(c, "تقرير متابعة حفظ القرآن الكريم", width / 2, height - 100, 20, font_name, colors.white, "center")
    draw_rtl(c, f"تاريخ التقرير: {date.today()}", width / 2, height - 155, 12, font_name, colors.HexColor("#334155"), "center")
    draw_rtl(c, "ملخص عام للأداء والحضور والحفظ", width / 2, height - 205, 15, font_name, green, "center")

    cards = [
        ("عدد الطلاب", summary["total_students"]),
        ("عدد التقييمات", summary["total_evals"]),
        ("المعدل العام", summary["avg_note"]),
        ("نسبة الحضور", f'{summary["attendance_rate"]}%'),
        ("مجموع الصفحات", summary["total_pages"]),
        ("مجموع الأخطاء", summary["total_mistakes"]),
    ]
    y = height - 270
    for label, value in cards:
        c.setFillColor(colors.white)
        c.setStrokeColor(border)
        c.roundRect(120, y - 18, width - 240, 40, 6, stroke=1, fill=1)
        draw_rtl(c, label, width - 165, y - 3, 12, font_name, dark, "right")
        draw_rtl(c, value, 210, y - 3, 13, font_name, green, "center")
        y -= 55

    draw_rtl(c, "ملاحظة الخصوصية", width / 2, 140, 13, font_name, green, "center")
    draw_rtl(c, "تظهر الرموز فقط في المبيانات، بينما تبقى الأسماء في الجداول الإدارية داخل التقرير.", width / 2, 115, 10, font_name, colors.HexColor("#334155"), "center")
    footer(1)
    c.showPage()

    # Page 2: students summary table with names
    c.setFillColor(colors.white)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    draw_rtl(c, "جدول ملخص الطلاب", width / 2, height - 55, 17, font_name, green, "center")
    headers = ["الرمز", "الاسم الكامل", "عدد التقييمات", "الصفحات", "الأخطاء", "المعدل"]
    rows = [[r["student_code"], r["full_name"], r["total_evals"], r["pages"], r["mistakes"], r["avg_note"]] for r in progress[:28]]
    table_data = [[rtl_text(x) for x in headers]] + [[rtl_text(x) for x in row] for row in rows]
    t = Table(table_data, colWidths=[62, 150, 85, 70, 70, 70], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, border),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    tw, th = t.wrapOn(c, width - 80, height - 120)
    t.drawOn(c, 40, height - 95 - th)
    footer(2)
    c.showPage()

    # Page 3: latest evaluations table with names
    c.setFillColor(colors.white)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    draw_rtl(c, "آخر التقييمات المسجلة", width / 2, height - 55, 17, font_name, green, "center")
    headers = ["التاريخ", "الاسم", "السورة", "الصفحات", "الأخطاء", "النقطة", "الحضور", "الملاحظة"]
    rows = [[r["eval_date"], r["full_name"], r["surah"], r["pages"], r["mistakes"], r["note"], r["attendance"], r["remark"]] for r in last_evals[:22]]
    table_data = [[rtl_text(x) for x in headers]] + [[rtl_text(x) for x in row] for row in rows]
    t = Table(table_data, colWidths=[65, 105, 65, 52, 52, 52, 55, 95], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, border),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    tw, th = t.wrapOn(c, width - 50, height - 120)
    t.drawOn(c, 25, height - 95 - th)
    footer(3)
    c.showPage()

    codes = [str(r["student_code"]) for r in progress[:10]]
    pages = [r["pages"] or 0 for r in progress[:10]]
    notes = [r["avg_note"] or 0 for r in progress[:10]]

    # Page 4: pages chart with codes only
    c.setPageSize(landscape(A4))
    lw, lh = landscape(A4)
    c.setFillColor(colors.white)
    c.rect(0, 0, lw, lh, stroke=0, fill=1)
    draw_rtl(c, "مجموع الصفحات المحفوظة حسب رمز الطالب", lw / 2, lh - 45, 17, font_name, green, "center")
    chart = make_chart_image(codes, pages, kind="bar")
    c.drawImage(ImageReader(chart), 55, 65, width=lw - 110, height=lh - 135, preserveAspectRatio=True, anchor="c")
    c.setStrokeColor(border)
    c.line(40, 35, lw - 40, 35)
    draw_rtl(c, "الصفحة 4", lw / 2, 20, 9, font_name, colors.HexColor("#64748b"), "center")
    c.showPage()

    # Page 5: notes chart with codes only
    c.setPageSize(landscape(A4))
    c.setFillColor(colors.white)
    c.rect(0, 0, lw, lh, stroke=0, fill=1)
    draw_rtl(c, "معدل النقط حسب رمز الطالب", lw / 2, lh - 45, 17, font_name, green, "center")
    chart = make_chart_image(codes, notes, kind="line")
    c.drawImage(ImageReader(chart), 55, 65, width=lw - 110, height=lh - 135, preserveAspectRatio=True, anchor="c")
    c.setStrokeColor(border)
    c.line(40, 35, lw - 40, 35)
    draw_rtl(c, "الصفحة 5", lw / 2, 20, 9, font_name, colors.HexColor("#64748b"), "center")
    c.showPage()

    c.save()
    buffer.seek(0)
    headers = {"Content-Disposition": "attachment; filename=quran_report_professional.pdf"}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)


@app.get("/api/dashboard")
def api_dashboard():
    conn = db_conn()
    data = conn.execute("""
        SELECT s.student_code, SUM(e.pages) AS pages, ROUND(AVG(e.note),2) AS avg_note, SUM(e.mistakes) AS mistakes
        FROM students s
        LEFT JOIN evaluations e ON e.student_id = s.id
        GROUP BY s.id
        ORDER BY s.student_code
    """).fetchall()
    conn.close()
    return [dict(row) for row in data]

@app.post("/students/edit/{student_id}")
def edit_student(
    student_id: int,
    student_code: str = Form(""),
    full_name: str = Form(...),
    age: int = Form(0),
    level: str = Form("مبتدئ"),
    phone_guardian: str = Form("")
):
    conn = db_conn()
    conn.execute("""
        UPDATE students
        SET student_code=?, full_name=?, age=?, level=?, phone_guardian=?
        WHERE id=?
    """, (student_code.strip(), full_name, age, level, phone_guardian, student_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/students", status_code=303)


@app.post("/evaluations/edit/{evaluation_id}")
def edit_evaluation(
    evaluation_id: int,
    student_id: int = Form(...),
    eval_date: str = Form(...),
    surah: str = Form(...),
    ayat_from: str = Form(""),
    ayat_to: str = Form(""),
    pages: float = Form(0),
    mistakes: int = Form(0),
    attendance: str = Form("حاضر"),
    revision: str = Form("نعم"),
    note: float = Form(0),
    remark: str = Form("")
):
    conn = db_conn()
    conn.execute("""
        UPDATE evaluations
        SET student_id=?, eval_date=?, surah=?, ayat_from=?, ayat_to=?, pages=?, mistakes=?, attendance=?, revision=?, note=?, remark=?
        WHERE id=?
    """, (student_id, eval_date, surah, ayat_from, ayat_to, pages, mistakes, attendance, revision, note, remark, evaluation_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/evaluations", status_code=303)


@app.post("/evaluations/delete/{evaluation_id}")
def delete_evaluation(evaluation_id: int):
    conn = db_conn()
    conn.execute("DELETE FROM evaluations WHERE id=?", (evaluation_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/evaluations", status_code=303)
