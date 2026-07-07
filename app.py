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


@app.get("/report/pdf")
def report_pdf():
    conn = db_conn()
    summary = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM students) AS total_students,
            (SELECT COUNT(*) FROM evaluations) AS total_evals,
            ROUND(COALESCE(AVG(note), 0), 2) AS avg_note,
            ROUND(COALESCE(SUM(pages), 0), 2) AS total_pages,
            COALESCE(SUM(mistakes), 0) AS total_mistakes
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
    plt.rcParams["font.family"] = "DejaVu Sans"
    with PdfPages(buffer) as pdf:
        # صفحة الغلاف والملخص
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("#f6fbf8")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0.06, 0.06), 0.88, 0.88, fill=False, linewidth=2, edgecolor="#0f766e"))
        ax.add_patch(plt.Rectangle((0.06, 0.86), 0.88, 0.08, color="#0f766e"))
        fig.text(0.5, 0.895, ar("تقرير متابعة حفظ القرآن الكريم"), ha="center", va="center", fontsize=22, color="white", weight="bold")
        fig.text(0.5, 0.835, ar(f"تاريخ التقرير: {date.today()}"), ha="center", fontsize=12, color="#334155")
        fig.text(0.5, 0.79, ar("ملخص عام للأداء والحضور والحفظ"), ha="center", fontsize=14, color="#0f766e", weight="bold")

        cards = [
            ("عدد الطلاب", summary["total_students"]),
            ("عدد التقييمات", summary["total_evals"]),
            ("المعدل العام", summary["avg_note"]),
            ("مجموع الصفحات", summary["total_pages"]),
            ("مجموع الأخطاء", summary["total_mistakes"]),
        ]
        y = 0.69
        for label, value in cards:
            ax.add_patch(plt.Rectangle((0.18, y-0.025), 0.64, 0.045, color="white", ec="#dbe7e2"))
            fig.text(0.70, y, ar(label), fontsize=13, weight="bold", ha="right", color="#0f172a")
            fig.text(0.30, y, ar(value), fontsize=13, ha="right", color="#0f766e", weight="bold")
            y -= 0.065

        fig.text(0.5, 0.34, ar("ملاحظة الخصوصية"), ha="center", fontsize=14, weight="bold", color="#0f766e")
        fig.text(0.5, 0.30, ar("هذا التقرير يتضمن الأسماء الكاملة بغرض التسليم الفردي أو المتابعة الإدارية."), ha="center", fontsize=11, color="#334155")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # جدول تفصيلي بأسماء الطلاب
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.text(0.5, 0.94, ar("جدول ملخص الطلاب"), ha="center", fontsize=18, weight="bold")
        ax_table = fig.add_axes([0.04, 0.08, 0.92, 0.78])
        ax_table.axis("off")
        headers = [ar(x) for x in ["الرمز", "الاسم الكامل", "عدد التقييمات", "الصفحات", "الأخطاء", "المعدل"]]
        rows = [[ar(r["student_code"]), ar(r["full_name"]), ar(r["total_evals"]), ar(r["pages"]), ar(r["mistakes"]), ar(r["avg_note"])] for r in progress]
        if rows:
            table = ax_table.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1, 1.45)
        else:
            ax_table.text(0.5, 0.5, ar("لا توجد بيانات بعد"), ha="center", va="center", fontsize=14)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # آخر التقييمات
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.text(0.5, 0.94, ar("آخر التقييمات المسجلة"), ha="center", fontsize=18, weight="bold")
        ax_table = fig.add_axes([0.03, 0.06, 0.94, 0.82])
        ax_table.axis("off")
        headers = [ar(x) for x in ["التاريخ", "الاسم", "السورة", "الصفحات", "الأخطاء", "النقطة", "الحضور", "الملاحظة"]]
        rows = [[ar(r["eval_date"]), ar(r["full_name"]), ar(r["surah"]), ar(r["pages"]), ar(r["mistakes"]), ar(r["note"]), ar(r["attendance"]), ar(r["remark"])] for r in last_evals]
        if rows:
            table = ax_table.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
            table.auto_set_font_size(False)
            table.set_fontsize(8)
            table.scale(1, 1.35)
        else:
            ax_table.text(0.5, 0.5, ar("لا توجد تقييمات بعد"), ha="center", va="center", fontsize=14)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        names = [ar(r["full_name"]) for r in progress[:10]]
        pages = [r["pages"] or 0 for r in progress[:10]]
        notes = [r["avg_note"] or 0 for r in progress[:10]]

        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.bar(names, pages)
        ax.set_title(ar("مجموع الصفحات المحفوظة حسب الطالب"), fontsize=16, weight="bold")
        ax.set_ylabel(ar("عدد الصفحات"))
        ax.tick_params(axis="x", rotation=30)
        ax.grid(axis="y", alpha=0.25)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.plot(names, notes, marker="o", linewidth=2)
        ax.set_title(ar("معدل النقط حسب الطالب"), fontsize=16, weight="bold")
        ax.set_ylabel(ar("النقطة"))
        ax.tick_params(axis="x", rotation=30)
        ax.grid(alpha=0.25)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

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
