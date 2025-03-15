from flask import Flask, render_template, request, redirect, url_for
import pymysql
from flask import Response
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import letter
import io
import arabic_reshaper
from bidi.algorithm import get_display
app = Flask(__name__)

# إعداد الاتصال بقاعدة البيانات MySQL
db = pymysql.connect(
    host="localhost",
    user="root",  # ضع اسم مستخدم MySQL
    password="",  # ضع كلمة مرور MySQL إذا كانت موجودة
    database="training_db",
    cursorclass=pymysql.cursors.DictCursor
)

# وظيفة لجلب المدارس
def get_schools():
    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM schools")
        return cursor.fetchall()

# وظيفة لجلب الأقسام
def get_departments():
    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM departments")
        return cursor.fetchall()

@app.route('/')
def home():
    return render_template('home.html')
from pymysql.err import IntegrityError

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        national_id = request.form['national_id']  # جلب الرقم الوطني
        department_id = request.form['department']
        year = request.form['year']
        school_id = request.form['school']

        try:
            with db.cursor() as cursor:
                # 1. التحقق من التكرار أولًا
                cursor.execute("SELECT id FROM students WHERE national_id = %s", (national_id,))
                if cursor.fetchone():
                    return "الرقم الوطني مسجل مسبقًا!"

                # 2. التحقق من السعة
                cursor.execute("""
                    SELECT max_students, 
                    (SELECT COUNT(*) FROM students 
                     WHERE school_id = %s AND department_id = %s AND year = %s) AS current
                    FROM school_department 
                    WHERE school_id = %s AND department_id = %s AND year = %s
                """, (school_id, department_id, year, school_id, department_id, year))
                school_data = cursor.fetchone()

                if school_data and school_data["current"] < school_data["max_students"]:
                    # 3. الإدراج مع الرقم الوطني
                    cursor.execute("""
                        INSERT INTO students 
                        (name, national_id, department_id, year, school_id) 
                        VALUES (%s, %s, %s, %s, %s)
                    """, (name, national_id, department_id, year, school_id))
                    db.commit()
                    return f"تم تسجيل {name} بنجاح!"
                else:
                    return "السعة ممتلئة!"

        except IntegrityError as e:
            db.rollback()
            if 'national_id' in str(e):
                return "الرقم الوطني مكرر!"
            else:
                return f"خطأ في قاعدة البيانات: {str(e)}"

    departments = get_departments()
    return render_template('register.html', departments=departments)
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        school_name = request.form['school_name']
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO schools (name) VALUES (%s)", (school_name,))
            db.commit()
        return redirect(url_for('admin'))

    with db.cursor() as cursor:
        # جلب جميع المدارس
        cursor.execute("SELECT id, name FROM schools")
        schools = cursor.fetchall()

        # جلب جميع الأقسام
        cursor.execute("SELECT id, name FROM departments")
        departments = cursor.fetchall()

        # جلب جميع عمليات الربط بين المدارس والأقسام مع تجميع المدارس في عمود واحد
        cursor.execute("""
            SELECT d.name AS department_name, sd.year, sd.max_students,
                   GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR ', ') AS school_names
            FROM school_department sd
            JOIN departments d ON sd.department_id = d.id
            JOIN schools s ON sd.school_id = s.id
            GROUP BY sd.department_id, sd.year, sd.max_students
        """)
        school_departments = cursor.fetchall()

    return render_template('admin.html', schools=schools, departments=departments, school_departments=school_departments)


@app.route('/students', methods=['GET'])
def students():
    year = request.args.get('year', '')
    department_id = request.args.get('department_id', '')
    school_id = request.args.get('school_id', '')

    query = """
        SELECT students.name, students.national_id, students.year,
               departments.name AS department_name, schools.name AS school_name
        FROM students
        JOIN departments ON students.department_id = departments.id
        JOIN schools ON students.school_id = schools.id
        WHERE 1=1
    """
    params = []

    if year:
        query += " AND students.year = %s"
        params.append(year)

    if department_id:
        query += " AND students.department_id = %s"
        params.append(department_id)

    if school_id:
        query += " AND students.school_id = %s"
        params.append(school_id)

    with db.cursor() as cursor:
        cursor.execute(query, tuple(params))
        students = cursor.fetchall()

        cursor.execute("SELECT DISTINCT year FROM students")
        years = cursor.fetchall()

        cursor.execute("SELECT id, name FROM departments")
        departments = cursor.fetchall()

        cursor.execute("SELECT id, name FROM schools")
        schools = cursor.fetchall()

    return render_template('students.html', students=students, years=years, departments=departments, schools=schools)


@app.route('/register_student', methods=['POST'])
def register_student():
    student_name = request.form['student_name']
    student_nid = request.form['student_nid']
    department_id = request.form['department_id']
    year = request.form['year']
    school_id = request.form['school_id']

    with db.cursor() as cursor:
        # التحقق من الحد الأقصى للطلاب
        cursor.execute("""
            SELECT max_students, 
            (SELECT COUNT(*) FROM students WHERE school_id = %s AND department_id = %s AND year = %s) AS current_students
            FROM school_department 
            WHERE school_id = %s AND department_id = %s AND year = %s
        """, (school_id, department_id, year, school_id, department_id, year))
        school_data = cursor.fetchone()

        if school_data and school_data["current_students"] < school_data["max_students"]:
            cursor.execute("INSERT INTO students (name, national_id, department_id, year, school_id) VALUES (%s, %s, %s, %s, %s)",
                           (student_name, student_nid, department_id, year, school_id))
            db.commit()
            return "تم تسجيل الطالب بنجاح!"
        else:
            return "هذه المدرسة ممتلئة ولا يمكن التسجيل بها."





@app.route('/add_department', methods=['POST'])
def add_department():
    department_name = request.form['department_name']
    with db.cursor() as cursor:
        cursor.execute("INSERT INTO departments (name) VALUES (%s)", (department_name,))
        db.commit()
    return redirect(url_for('admin'))

@app.route('/assign_school_department', methods=['POST'])
def assign_school_department():
    try:
        department_id = request.form['department_id']
        year = request.form['year']
        school_ids = request.form.getlist('school_ids')  # قائمة المدارس المحددة
        max_students = request.form['max_students']  # العدد الذي سيتم تطبيقه على جميع المدارس

        if not school_ids:
            return "يجب اختيار مدرسة واحدة على الأقل!", 400

        with db.cursor() as cursor:
            for school_id in school_ids:
                cursor.execute("""
                    SELECT COUNT(*) AS count FROM school_department 
                    WHERE school_id = %s AND department_id = %s AND year = %s
                """, (school_id, department_id, year))
                result = cursor.fetchone()

                if result["count"] == 0:  # إضافة فقط إذا لم يكن موجودًا بالفعل
                    cursor.execute("""
                        INSERT INTO school_department (school_id, department_id, year, max_students) 
                        VALUES (%s, %s, %s, %s)
                    """, (school_id, department_id, year, max_students))
                else:
                    # تحديث الحد الأقصى للطلاب إذا كان الإدخال موجودًا بالفعل
                    cursor.execute("""
                        UPDATE school_department 
                        SET max_students = %s 
                        WHERE school_id = %s AND department_id = %s AND year = %s
                    """, (max_students, school_id, department_id, year))

            db.commit()

        return redirect(url_for('admin'))  # العودة إلى صفحة الإدارة بعد الإضافة

    except Exception as e:
        return f"حدث خطأ: {str(e)}", 400


@app.route('/add_school', methods=['POST'])
def add_school():
    school_name = request.form['school_name']
    with db.cursor() as cursor:
        cursor.execute("INSERT INTO schools (name) VALUES (%s)", (school_name,))
        db.commit()
    return redirect(url_for('admin'))



@app.route('/get_schools', methods=['POST'])
def get_schools():
    department_id = request.json.get('department_id')
    year = request.json.get('year')

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT s.id, s.name
            FROM school_department sd
            JOIN schools s ON sd.school_id = s.id
            WHERE sd.department_id = %s AND sd.year = %s
        """, (department_id, year))
        schools = cursor.fetchall()

    return {"schools": schools}


# تسجيل الخط العربي
pdfmetrics.registerFont(TTFont('ArabicFont', 'fonts/Amiri-Regular.ttf'))  # تأكد من وضع الخط في المسار الصحيح

def draw_arabic_text(pdf, x, y, text, font="ArabicFont", size=12):
    """ وظيفة لإعادة تشكيل وتصحيح اتجاه النصوص العربية """
    reshaped_text = arabic_reshaper.reshape(text)  # إعادة تشكيل الأحرف العربية
    bidi_text = get_display(reshaped_text)  # تصحيح اتجاه النص
    pdf.setFont(font, size)
    pdf.drawString(x, y, bidi_text)

@app.route('/export_pdf')
def export_pdf():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("قائمة الطلاب المسجلين")

    # استخدام الخط العربي
    draw_arabic_text(pdf, 200, 750, "قائمة الطلاب المسجلين", size=16)

    # جلب بيانات الطلاب
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT students.name, students.national_id, students.year,
                   departments.name AS department_name, schools.name AS school_name
            FROM students
            JOIN departments ON students.department_id = departments.id
            JOIN schools ON students.school_id = schools.id
        """)
        students = cursor.fetchall()

    # رسم الجدول
    x_offset = 50
    y_offset = 700
    line_height = 25

    draw_arabic_text(pdf, x_offset, y_offset, "الاسم")
    draw_arabic_text(pdf, x_offset + 150, y_offset, "الرقم القومي")
    draw_arabic_text(pdf, x_offset + 300, y_offset, "القسم")
    draw_arabic_text(pdf, x_offset + 450, y_offset, "الفرقة")
    draw_arabic_text(pdf, x_offset + 550, y_offset, "المدرسة")
    y_offset -= line_height

    for student in students:
        draw_arabic_text(pdf, x_offset, y_offset, student['name'])
        pdf.drawString(x_offset + 150, y_offset, student['national_id'])  # لا يحتاج تصحيح
        draw_arabic_text(pdf, x_offset + 300, y_offset, student['department_name'])
        draw_arabic_text(pdf, x_offset + 450, y_offset, student['year'])
        draw_arabic_text(pdf, x_offset + 550, y_offset, student['school_name'])
        y_offset -= line_height

    pdf.save()
    buffer.seek(0)

    return Response(buffer, mimetype="application/pdf", headers={"Content-Disposition": "attachment;filename=students_list.pdf"})






if __name__ == '__main__':
    app.run(debug=True)
