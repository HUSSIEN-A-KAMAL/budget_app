import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database import SessionLocal, ensure_schema_up_to_date
from models.user import BudgetUser, GeneralDepartmentLookup, SystemLookupOption
from models.budget import DepartmentBudget, BudgetLineItem, BudgetGovernanceConfig

# Standard scrypt hash for password "123456"
DEFAULT_MOCK_PASSWORD_HASH = (
    "scrypt:32768:8:1$OCZrvWixYvLRW3Mm$"
    "8b6444b55240aceca7fb5441db8239ee7c892368678f84e3be66b552a68cc1fe"
    "9ddd1ec614f7df17bb5534faf3e46fec9c8bc31fe7c60e9458f9e3b2c64094a4"
)


def initialize_and_seed_standalone_db():
    """
    Initializes the dedicated standalone SQLite database (budget_standalone.db)
    and populates it with 100% anonymized mock personnel data (at least 1 GM and
    2 standard employees per general department), dynamic lookup options,
    RBAC governance configs, and departmental budget allocations & line items.
    """
    ensure_schema_up_to_date()
    db = SessionLocal()
    try:
        # 1. Seed General Departments Lookup & Dynamic SystemLookupOption
        general_departments = [
            "الأمن",
            "الاستكشاف",
            "الإدارة العامة لتكنولوجيا المعلومات",
            "الإدارة العامة للشئون القانونية",
            "الإدارة العامة للمشروعات",
            "الحقول",
            "السلامة والصحة المهنية وحماية",
            "الشئون الإدارية",
            "الشئون المالية",
            "العقود والمناقصات",
            "العمليات",
            "المراجعة الداخلية",
            "المشروعات والنقل",
            "المهمات",
            "رئيس مجلس الإدارة والعضو المنتدب",
            "سلامة العمليات",
        ]
        for dept_name in general_departments:
            if not db.query(GeneralDepartmentLookup).filter_by(name=dept_name).first():
                db.add(GeneralDepartmentLookup(name=dept_name, is_active=True))
            if not db.query(SystemLookupOption).filter_by(category="DEPARTMENT", value=dept_name).first():
                db.add(SystemLookupOption(category="DEPARTMENT", value=dept_name, is_active=True))

        default_locations = [
            "المركز الرئيسي - القاهرة",
            "حقول الصحراء الغربية",
            "حقول خليج السويس",
            "موقع رأس غارب",
            "مستودعات السويس المركزية",
            "مكتب الإسكندرية الإقليمي",
        ]
        for loc in default_locations:
            if not db.query(SystemLookupOption).filter_by(category="WORK_LOCATION", value=loc).first():
                db.add(SystemLookupOption(category="WORK_LOCATION", value=loc, is_active=True))

        default_job_titles = [
            "مدير النظام وتقنية المعلومات",
            "مساعد رئيس الشركة",
            "مدير عام الإدارة",
            "مسؤول السلامة والصحة المهنية (HSE)",
            "مدير إدارة فرعية",
            "رئيس قسم",
            "أخصائي أول موازنة وتخطيط",
            "أخصائي شئون إدارية",
            "أخصائي علاقات عامة وخدمات",
            "أخصائي تدريب وتطوير",
            "مهندس نظم ومعلومات أول",
            "باحث قانوني أول",
            "مهندس مشروعات أول",
            "محاسب مالي ومراقب تكاليف",
            "أخصائي عقود ومناقصات",
            "مراجع داخلي أول",
            "أخصائي مراقبة مخزون ومهمات",
            "جيولوجي استكشاف أول",
            "مهندس إنتاج وحقول",
            "مهندس عمليات رئيسي",
            "مهندس سلامة عمليات",
            "مسؤول أمن صناعي",
            "منسق مكتب فني",
        ]
        for jt in default_job_titles:
            if not db.query(SystemLookupOption).filter_by(category="JOB_TITLE", value=jt).first():
                db.add(SystemLookupOption(category="JOB_TITLE", value=jt, is_active=True))

        default_sub_departments = [
            "نظم المعلومات الإدارية",
            "الخدمات الإدارية",
            "العلاقات العامة والخدمات",
            "التدريب والتنظيم",
            "حماية البيئة",
            "الصحة المهنية",
            "المكتب الفني",
            "متابعة اللجان",
            "أمن المنشآت",
            "تصاريح الحقول",
            "البنية التحتية والشبكات",
            "تطوير النظم وقواعد البيانات",
            "العقود والفتاوى",
            "القضايا والتحقيقات",
            "التخطيط ومتابعة المشروعات",
            "التصميمات والتركيبات",
            "الموازنة والتكاليف",
            "الحسابات العامة",
            "الطرح والترسية",
            "متابعة العقود",
            "المراجعة المالية",
            "مراجعة العقود والمشتريات",
            "مراقبة المخزون",
            "المشتريات المحلية",
            "الجيوفيزياء",
            "تقييم الطبقات",
            "صيانة الآبار",
            "محطات المعالجة",
            "هندسة الإنتاج",
            "التشغيل والصيانة",
            "تحليل المخاطر",
            "التكامل الميكانيكي",
            "النقل والمعدات الثقيلة",
            "حركة الأسطول",
        ]
        for sd in default_sub_departments:
            if not db.query(SystemLookupOption).filter_by(category="SUB_DEPARTMENT", value=sd).first():
                db.add(SystemLookupOption(category="SUB_DEPARTMENT", value=sd, is_active=True))

        default_roles = [
            "employee",
            "dept_gm",
            "hse_officer",
            "admin",
        ]
        for rl in default_roles:
            if not db.query(SystemLookupOption).filter_by(category="ROLE", value=rl).first():
                db.add(SystemLookupOption(category="ROLE", value=rl, is_active=True))

        # 2. Seed Anonymized Mock Users (System Admin + 1 GM & >=2 Employees per Department)
        users_seed = [
            # --- System Administrator (7071) ---
            {
                "emp_id": 7071,
                "name": "م. طارق محمود العلي (مدير النظام)",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "admin",
                "general_dept_name": "الشئون الإدارية",
                "dept_name": "نظم المعلومات الإدارية",
                "job_title": "مدير النظام وتقنية المعلومات",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090007071",
                "email": "admin.7071@petro-demo.local",
            },

            # --- 1. الشئون الإدارية (1 GM + 3 Employees) ---
            {
                "emp_id": 10033,
                "name": "أ. خالد عبد الرحمن المنشاوي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الشئون الإدارية",
                "dept_name": "الشئون الإدارية",
                "job_title": "مساعد رئيس الشركة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090010033",
                "email": "gm.admin@petro-demo.local",
            },
            {
                "emp_id": 268,
                "name": "أ. رامي عادل الشاذلي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الشئون الإدارية",
                "dept_name": "الخدمات الإدارية",
                "job_title": "أخصائي شئون إدارية",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090000268",
                "email": "emp.268@petro-demo.local",
            },
            {
                "emp_id": 43,
                "name": "أ. سارة نبيل الكيلاني",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الشئون الإدارية",
                "dept_name": "العلاقات العامة والخدمات",
                "job_title": "أخصائي علاقات عامة وخدمات",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090000043",
                "email": "emp.43@petro-demo.local",
            },
            {
                "emp_id": 45,
                "name": "أ. تامر فؤاد الجوهري",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الشئون الإدارية",
                "dept_name": "التدريب والتنظيم",
                "job_title": "أخصائي تدريب وتطوير",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090000045",
                "email": "emp.45@petro-demo.local",
            },

            # --- 2. السلامة والصحة المهنية وحماية (1 HSE Officer/GM + 2 Employees) ---
            {
                "emp_id": 10019,
                "name": "م. كريم سامي النجار",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "hse_officer",
                "general_dept_name": "السلامة والصحة المهنية وحماية",
                "dept_name": "السلامة والصحة المهنية وحماية",
                "job_title": "مسؤول السلامة والصحة المهنية (HSE)",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090010019",
                "email": "hse.10019@petro-demo.local",
            },
            {
                "emp_id": 2011,
                "name": "م. شادي محسن زهران",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "السلامة والصحة المهنية وحماية",
                "dept_name": "حماية البيئة",
                "job_title": "مهندس سلامة عمليات",
                "work_location": "حقول الصحراء الغربية",
                "phone": "01090002011",
                "email": "emp.2011@petro-demo.local",
            },
            {
                "emp_id": 2012,
                "name": "م. ندى أشرف التهامي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "السلامة والصحة المهنية وحماية",
                "dept_name": "الصحة المهنية",
                "job_title": "أخصائي أول موازنة وتخطيط",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002012",
                "email": "emp.2012@petro-demo.local",
            },

            # --- 3. رئيس مجلس الإدارة والعضو المنتدب (1 GM + 2 Employees) ---
            {
                "emp_id": 10041,
                "name": "م. جلال الدين فاروق سليم",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "رئيس مجلس الإدارة والعضو المنتدب",
                "dept_name": "المكتب الفني لرئيس الشركة",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090010041",
                "email": "gm.chairman@petro-demo.local",
            },
            {
                "emp_id": 2021,
                "name": "أ. نهى كمال الديب",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "رئيس مجلس الإدارة والعضو المنتدب",
                "dept_name": "المكتب الفني",
                "job_title": "منسق مكتب فني",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002021",
                "email": "emp.2021@petro-demo.local",
            },
            {
                "emp_id": 2022,
                "name": "أ. مروان يحيى الشناوي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "رئيس مجلس الإدارة والعضو المنتدب",
                "dept_name": "متابعة اللجان",
                "job_title": "أخصائي أول موازنة وتخطيط",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002022",
                "email": "emp.2022@petro-demo.local",
            },

            # --- 4. الأمن (1 GM + 2 Employees) ---
            {
                "emp_id": 10051,
                "name": "لواء. شريف عزت الأنصاري",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الأمن",
                "dept_name": "الأمن العام",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090010051",
                "email": "gm.security@petro-demo.local",
            },
            {
                "emp_id": 2031,
                "name": "أ. حازم صبري غنيم",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الأمن",
                "dept_name": "أمن المنشآت",
                "job_title": "مسؤول أمن صناعي",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002031",
                "email": "emp.2031@petro-demo.local",
            },
            {
                "emp_id": 2032,
                "name": "أ. وليد مختار عبد الباقي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الأمن",
                "dept_name": "تصاريح الحقول",
                "job_title": "مسؤول أمن صناعي",
                "work_location": "حقول الصحراء الغربية",
                "phone": "01090002032",
                "email": "emp.2032@petro-demo.local",
            },

            # --- 5. الإدارة العامة لتكنولوجيا المعلومات (1 GM + 2 Employees) ---
            {
                "emp_id": 50,
                "name": "م. وائل ممدوح عبد السلام",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الإدارة العامة لتكنولوجيا المعلومات",
                "dept_name": "تكنولوجيا المعلومات",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090000050",
                "email": "gm.it@petro-demo.local",
            },
            {
                "emp_id": 2041,
                "name": "م. مازن إيهاب السعدني",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الإدارة العامة لتكنولوجيا المعلومات",
                "dept_name": "البنية التحتية والشبكات",
                "job_title": "مهندس نظم ومعلومات أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002041",
                "email": "emp.2041@petro-demo.local",
            },
            {
                "emp_id": 2042,
                "name": "م. ريم حاتم الفرماوي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الإدارة العامة لتكنولوجيا المعلومات",
                "dept_name": "تطوير النظم وقواعد البيانات",
                "job_title": "مهندس نظم ومعلومات أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002042",
                "email": "emp.2042@petro-demo.local",
            },

            # --- 6. الإدارة العامة للشئون القانونية (1 GM + 2 Employees) ---
            {
                "emp_id": 107,
                "name": "المستشار. نبيل فوزي علام",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الإدارة العامة للشئون القانونية",
                "dept_name": "الشئون القانونية",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090000107",
                "email": "gm.legal@petro-demo.local",
            },
            {
                "emp_id": 2051,
                "name": "أ. باسل حمدي الشرقاوي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الإدارة العامة للشئون القانونية",
                "dept_name": "العقود والفتاوى",
                "job_title": "باحث قانوني أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002051",
                "email": "emp.2051@petro-demo.local",
            },
            {
                "emp_id": 2052,
                "name": "أ. مريم شوقي عبد الوهاب",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الإدارة العامة للشئون القانونية",
                "dept_name": "القضايا والتحقيقات",
                "job_title": "باحث قانوني أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002052",
                "email": "emp.2052@petro-demo.local",
            },

            # --- 7. الإدارة العامة للمشروعات (1 GM + 2 Employees) ---
            {
                "emp_id": 118,
                "name": "م. مدحت رشاد القاضي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الإدارة العامة للمشروعات",
                "dept_name": "المشروعات الهندسية",
                "job_title": "مدير عام الإدارة",
                "work_location": "موقع رأس غارب",
                "phone": "01090000118",
                "email": "gm.projects@petro-demo.local",
            },
            {
                "emp_id": 2061,
                "name": "م. زياد طلال الدمرداش",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الإدارة العامة للمشروعات",
                "dept_name": "التخطيط ومتابعة المشروعات",
                "job_title": "مهندس مشروعات أول",
                "work_location": "موقع رأس غارب",
                "phone": "01090002061",
                "email": "emp.2061@petro-demo.local",
            },
            {
                "emp_id": 2062,
                "name": "م. سلمى عاطف البنا",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الإدارة العامة للمشروعات",
                "dept_name": "التصميمات والتركيبات",
                "job_title": "مهندس مشروعات أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002062",
                "email": "emp.2062@petro-demo.local",
            },

            # --- 8. الشئون المالية (1 GM + 2 Employees) ---
            {
                "emp_id": 10035,
                "name": "أ. عصام الدين توفيق مرسي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الشئون المالية",
                "dept_name": "الشئون المالية",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090010035",
                "email": "gm.finance@petro-demo.local",
            },
            {
                "emp_id": 2071,
                "name": "أ. أمير رؤوف الحلواني",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الشئون المالية",
                "dept_name": "الموازنة والتكاليف",
                "job_title": "محاسب مالي ومراقب تكاليف",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002071",
                "email": "emp.2071@petro-demo.local",
            },
            {
                "emp_id": 2072,
                "name": "أ. داليا وجيه الصاوي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الشئون المالية",
                "dept_name": "الحسابات العامة",
                "job_title": "محاسب مالي ومراقب تكاليف",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002072",
                "email": "emp.2072@petro-demo.local",
            },

            # --- 9. العقود والمناقصات (1 GM + 2 Employees) ---
            {
                "emp_id": 278,
                "name": "أ. شريف بهجت العيسوي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "العقود والمناقصات",
                "dept_name": "العقود والمناقصات",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090000278",
                "email": "gm.contracts@petro-demo.local",
            },
            {
                "emp_id": 2081,
                "name": "أ. إياد منير الغندور",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "العقود والمناقصات",
                "dept_name": "الطرح والترسية",
                "job_title": "أخصائي عقود ومناقصات",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002081",
                "email": "emp.2081@petro-demo.local",
            },
            {
                "emp_id": 2082,
                "name": "أ. هبة الله مجدي زكي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "العقود والمناقصات",
                "dept_name": "متابعة العقود",
                "job_title": "أخصائي عقود ومناقصات",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002082",
                "email": "emp.2082@petro-demo.local",
            },

            # --- 10. المراجعة الداخلية (1 GM + 2 Employees) ---
            {
                "emp_id": 10034,
                "name": "أ. عادل كمال الدماطي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "المراجعة الداخلية",
                "dept_name": "المراجعة الداخلية",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090010034",
                "email": "gm.audit@petro-demo.local",
            },
            {
                "emp_id": 2091,
                "name": "أ. فادي نصار مليكة",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "المراجعة الداخلية",
                "dept_name": "المراجعة المالية",
                "job_title": "مراجع داخلي أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002091",
                "email": "emp.2091@petro-demo.local",
            },
            {
                "emp_id": 2092,
                "name": "أ. ياسمين لطفي راشد",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "المراجعة الداخلية",
                "dept_name": "مراجعة العقود والمشتريات",
                "job_title": "مراجع داخلي أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002092",
                "email": "emp.2092@petro-demo.local",
            },

            # --- 11. المهمات (1 GM + 2 Employees) ---
            {
                "emp_id": 10021,
                "name": "م. منى جلال الحديدي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "المهمات",
                "dept_name": "المهمات والمخازن",
                "job_title": "مدير عام الإدارة",
                "work_location": "مستودعات السويس المركزية",
                "phone": "01090010021",
                "email": "gm.materials@petro-demo.local",
            },
            {
                "emp_id": 2101,
                "name": "أ. سامح زكريا الخولي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "المهمات",
                "dept_name": "مراقبة المخزون",
                "job_title": "أخصائي مراقبة مخزون ومهمات",
                "work_location": "مستودعات السويس المركزية",
                "phone": "01090002101",
                "email": "emp.2101@petro-demo.local",
            },
            {
                "emp_id": 2102,
                "name": "أ. هاجر علاء الدين بدر",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "المهمات",
                "dept_name": "المشتريات المحلية",
                "job_title": "أخصائي مراقبة مخزون ومهمات",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002102",
                "email": "emp.2102@petro-demo.local",
            },

            # --- 12. الاستكشاف (1 GM + 2 Employees) ---
            {
                "emp_id": 38,
                "name": "د. حاتم سليمان الفقي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الاستكشاف",
                "dept_name": "الاستكشاف الجيولوجي",
                "job_title": "مدير عام الإدارة",
                "work_location": "حقول الصحراء الغربية",
                "phone": "01090000038",
                "email": "gm.exploration@petro-demo.local",
            },
            {
                "emp_id": 2111,
                "name": "ج. عمر حمدان الألفي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الاستكشاف",
                "dept_name": "الجيوفيزياء",
                "job_title": "جيولوجي استكشاف أول",
                "work_location": "حقول الصحراء الغربية",
                "phone": "01090002111",
                "email": "emp.2111@petro-demo.local",
            },
            {
                "emp_id": 2112,
                "name": "ج. ليلى حسام الدين عزمي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الاستكشاف",
                "dept_name": "تقييم الطبقات",
                "job_title": "جيولوجي استكشاف أول",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002112",
                "email": "emp.2112@petro-demo.local",
            },

            # --- 13. الحقول (1 GM + 2 Employees) ---
            {
                "emp_id": 41,
                "name": "م. محمود عبد اللطيف شاهين",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "الحقول",
                "dept_name": "إدارة الحقول",
                "job_title": "مدير عام الإدارة",
                "work_location": "حقول الصحراء الغربية",
                "phone": "01090000041",
                "email": "gm.fields@petro-demo.local",
            },
            {
                "emp_id": 2121,
                "name": "م. بلال عبد المنعم حجازي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الحقول",
                "dept_name": "صيانة الآبار",
                "job_title": "مهندس إنتاج وحقول",
                "work_location": "حقول الصحراء الغربية",
                "phone": "01090002121",
                "email": "emp.2121@petro-demo.local",
            },
            {
                "emp_id": 2122,
                "name": "م. نبيل صابر الجندي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "الحقول",
                "dept_name": "محطات المعالجة",
                "job_title": "مهندس إنتاج وحقول",
                "work_location": "حقول خليج السويس",
                "phone": "01090002122",
                "email": "emp.2122@petro-demo.local",
            },

            # --- 14. العمليات (1 GM + 2 Employees) ---
            {
                "emp_id": 10036,
                "name": "م. كامل مصطفى الرفاعي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "العمليات",
                "dept_name": "العمليات والإنتاج",
                "job_title": "مدير عام الإدارة",
                "work_location": "حقول خليج السويس",
                "phone": "01090010036",
                "email": "gm.operations@petro-demo.local",
            },
            {
                "emp_id": 2131,
                "name": "م. رائد شوقي درويش",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "العمليات",
                "dept_name": "هندسة الإنتاج",
                "job_title": "مهندس عمليات رئيسي",
                "work_location": "حقول خليج السويس",
                "phone": "01090002131",
                "email": "emp.2131@petro-demo.local",
            },
            {
                "emp_id": 2132,
                "name": "م. هاني كرم عبد العزيز",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "العمليات",
                "dept_name": "التشغيل والصيانة",
                "job_title": "مهندس عمليات رئيسي",
                "work_location": "موقع رأس غارب",
                "phone": "01090002132",
                "email": "emp.2132@petro-demo.local",
            },

            # --- 15. سلامة العمليات (1 GM + 2 Employees) ---
            {
                "emp_id": 122,
                "name": "م. ياسر فريد السنباطي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "سلامة العمليات",
                "dept_name": "سلامة العمليات",
                "job_title": "مدير عام الإدارة",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090000122",
                "email": "gm.psm@petro-demo.local",
            },
            {
                "emp_id": 2141,
                "name": "م. أدهم مرتضى سالم",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "سلامة العمليات",
                "dept_name": "تحليل المخاطر",
                "job_title": "مهندس سلامة عمليات",
                "work_location": "حقول خليج السويس",
                "phone": "01090002141",
                "email": "emp.2141@petro-demo.local",
            },
            {
                "emp_id": 2142,
                "name": "م. رضوى ماجد عفيفي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "سلامة العمليات",
                "dept_name": "التكامل الميكانيكي",
                "job_title": "مهندس سلامة عمليات",
                "work_location": "المركز الرئيسي - القاهرة",
                "phone": "01090002142",
                "email": "emp.2142@petro-demo.local",
            },

            # --- 16. المشروعات والنقل (1 GM + 2 Employees) ---
            {
                "emp_id": 130,
                "name": "م. أشرف حمدي البلتاجي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "dept_gm",
                "general_dept_name": "المشروعات والنقل",
                "dept_name": "المشروعات والنقل",
                "job_title": "مدير عام الإدارة",
                "work_location": "موقع رأس غارب",
                "phone": "01090000130",
                "email": "gm.transport@petro-demo.local",
            },
            {
                "emp_id": 2151,
                "name": "م. حسام الدين وفيق عامر",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "المشروعات والنقل",
                "dept_name": "النقل والمعدات الثقيلة",
                "job_title": "مهندس مشروعات أول",
                "work_location": "موقع رأس غارب",
                "phone": "01090002151",
                "email": "emp.2151@petro-demo.local",
            },
            {
                "emp_id": 2152,
                "name": "أ. منصور رياض شلبي",
                "password_hash": DEFAULT_MOCK_PASSWORD_HASH,
                "role": "employee",
                "general_dept_name": "المشروعات والنقل",
                "dept_name": "حركة الأسطول",
                "job_title": "أخصائي أول موازنة وتخطيط",
                "work_location": "مستودعات السويس المركزية",
                "phone": "01090002152",
                "email": "emp.2152@petro-demo.local",
            },
        ]

        for u_data in users_seed:
            existing_u = db.get(BudgetUser, u_data["emp_id"])
            if not existing_u:
                db.add(BudgetUser(**u_data))
            else:
                # Overwrite with anonymized mock data to purge any sensitive real personnel records
                existing_u.name = u_data["name"]
                existing_u.role = u_data["role"]
                existing_u.general_dept_name = u_data["general_dept_name"]
                existing_u.dept_name = u_data["dept_name"]
                existing_u.job_title = u_data["job_title"]
                existing_u.work_location = u_data["work_location"]
                existing_u.phone = u_data["phone"]
                existing_u.email = u_data["email"]
                if existing_u.password_hash == "UNREGISTERED":
                    existing_u.password_hash = u_data["password_hash"]

        # 3. Seed & Synchronize BudgetGovernanceConfig with Anonymized Mock Names
        gov_configs_seed = [
            ("LEADERBOARD_VISIBILITY", "GLOBAL", None, None, True),
            ("HSE_OFFICER", "GLOBAL", 10019, "م. كريم سامي النجار", True),
            ("DEPT_GM", "الشئون الإدارية", 10033, "أ. خالد عبد الرحمن المنشاوي", True),
            ("DEPT_GM", "الأمن", 10051, "لواء. شريف عزت الأنصاري", True),
            ("DEPT_GM", "الإدارة العامة لتكنولوجيا المعلومات", 50, "م. وائل ممدوح عبد السلام", True),
            ("DEPT_GM", "الإدارة العامة للشئون القانونية", 107, "المستشار. نبيل فوزي علام", True),
            ("DEPT_GM", "الإدارة العامة للمشروعات", 118, "م. مدحت رشاد القاضي", True),
            ("DEPT_GM", "السلامة والصحة المهنية وحماية", 10019, "م. كريم سامي النجار", True),
            ("DEPT_GM", "الشئون المالية", 10035, "أ. عصام الدين توفيق مرسي", True),
            ("DEPT_GM", "العقود والمناقصات", 278, "أ. شريف بهجت العيسوي", True),
            ("DEPT_GM", "المراجعة الداخلية", 10034, "أ. عادل كمال الدماطي", True),
            ("DEPT_GM", "المهمات", 10021, "م. منى جلال الحديدي", True),
            ("DEPT_GM", "رئيس مجلس الإدارة والعضو المنتدب", 10041, "م. جلال الدين فاروق سليم", True),
            ("DEPT_GM", "الاستكشاف", 38, "د. حاتم سليمان الفقي", True),
            ("DEPT_GM", "الحقول", 41, "م. محمود عبد اللطيف شاهين", True),
            ("DEPT_GM", "العمليات", 10036, "م. كامل مصطفى الرفاعي", True),
            ("DEPT_GM", "المشروعات والنقل", 130, "م. أشرف حمدي البلتاجي", True),
            ("DEPT_GM", "سلامة العمليات", 122, "م. ياسر فريد السنباطي", True),
        ]

        for c_type, s_key, emp_id, emp_name, enabled in gov_configs_seed:
            exists_cfg = db.query(BudgetGovernanceConfig).filter_by(
                config_type=c_type,
                scope_key=s_key
            ).first()
            if not exists_cfg:
                db.add(BudgetGovernanceConfig(
                    config_type=c_type,
                    scope_key=s_key,
                    assigned_emp_id=emp_id,
                    assigned_emp_name=emp_name,
                    is_enabled=enabled,
                    updated_by="7071"
                ))
            else:
                exists_cfg.assigned_emp_id = emp_id
                exists_cfg.assigned_emp_name = emp_name

        # 4. Seed Department Budgets & Line Items
        budget_data = [
            {
                "general_dept_name": "الشئون الإدارية",
                "fiscal_year": 2026,
                "quarter": 3,
                "allocated_amount": 270000.0,
                "items": [
                    {
                        "item_name": "بند مهمات وأدوات مكتبية",
                        "allocated_amount": 50000.0,
                        "spent_amount": 32000.0,
                        "savings_narrative": "الاعتماد على التوقيع الرقمي وتقليص المطبوعات الورقية بنسبة 40%",
                        "gm_approved": True,
                        "gm_approved_by": "10033",
                        "hse_approved": True,
                        "hse_approved_by": "10019",
                        "workflow_status": "CLOSED",
                        "cost_avoidance_amount": 12000.0,
                    },
                    {
                        "item_name": "بند صيانة سيارات ووقود",
                        "allocated_amount": 120000.0,
                        "spent_amount": 95000.0,
                        "savings_narrative": "دمج خطوط سير المأموريات اليومية وترشيد الصيانة الدورية المجمعة",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": True,
                        "hse_approved_by": "10019",
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    },
                    {
                        "item_name": "توفير فى قيمة التأمينات",
                        "allocated_amount": 100000.0,
                        "spent_amount": 73500.0,
                        "savings_narrative": "الاعتماد على سياسة توفير النفقات ومراجعة التغطيات التأمينية",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    },
                ]
            },
            {
                "general_dept_name": "الإدارة العامة لتكنولوجيا المعلومات",
                "fiscal_year": 2026,
                "quarter": 3,
                "allocated_amount": 200000.0,
                "items": [
                    {
                        "item_name": "بند تراخيص وسيرفرات",
                        "allocated_amount": 200000.0,
                        "spent_amount": 160000.0,
                        "savings_narrative": "استبدال اشتراكات سحابية خارجية بخوادم محلية وسوفت وير مفتوح المصدر",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": True,
                        "hse_approved_by": "10019",
                        "workflow_status": "UNDER_EVALUATION",
                        "cost_avoidance_amount": 15000.0,
                    }
                ]
            },
            {
                "general_dept_name": "السلامة والصحة المهنية وحماية",
                "fiscal_year": 2026,
                "quarter": 3,
                "allocated_amount": 80000.0,
                "items": [
                    {
                        "item_name": "بند مهمات وقاية وتدريب",
                        "allocated_amount": 80000.0,
                        "spent_amount": 68000.0,
                        "savings_narrative": "إعادة التفاوض مع المورد المعتمد وتوريد خامات بالجملة",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            },
            {
                "general_dept_name": "العمليات",
                "fiscal_year": 2026,
                "quarter": 3,
                "allocated_amount": 350000.0,
                "items": [
                    {
                        "item_name": "بند قطع غيار ومعدات تشغيل الحقول",
                        "allocated_amount": 220000.0,
                        "spent_amount": 175000.0,
                        "savings_narrative": "إعادة تأهيل الصمامات والمضخات بالورش المركزية بدلاً من الاستيراد الفوري",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    },
                    {
                        "item_name": "بند إمدادات الطاقة والمولدات",
                        "allocated_amount": 130000.0,
                        "spent_amount": 102000.0,
                        "savings_narrative": "ضبط أحمال التشغيل الليلي وتطبيق جدول الصيانة الوقائية للمولدات",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            },
            {
                "general_dept_name": "الشئون المالية",
                "fiscal_year": 2026,
                "quarter": 3,
                "allocated_amount": 90000.0,
                "items": [
                    {
                        "item_name": "بند مطبوعات وسجلات مالية وأرشفة",
                        "allocated_amount": 90000.0,
                        "spent_amount": 64000.0,
                        "savings_narrative": "التحول إلى الأرشفة الإلكترونية الكاملة للفواتير ومستندات الصرف",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            },
            {
                "general_dept_name": "الشئون الإدارية",
                "fiscal_year": 2026,
                "quarter": 4,
                "allocated_amount": 185000.0,
                "items": [
                    {
                        "item_name": "بند مهمات وأدوات مكتبية",
                        "allocated_amount": 55000.0,
                        "spent_amount": 33000.0,
                        "savings_narrative": "تعميم الدورة المستندية الإلكترونية عبر بوابة العاملين وتقليل الاستهلاك الورقي",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    },
                    {
                        "item_name": "بند صيانة سيارات ووقود",
                        "allocated_amount": 130000.0,
                        "spent_amount": 98000.0,
                        "savings_narrative": "تطبيق منظومة تتبع وجدولة أتوبيسات الورديات وتخفيض رحلات الطوارئ الفردية",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            },
            {
                "general_dept_name": "الإدارة العامة لتكنولوجيا المعلومات",
                "fiscal_year": 2026,
                "quarter": 4,
                "allocated_amount": 240000.0,
                "items": [
                    {
                        "item_name": "بند تراخيص وسيرفرات",
                        "allocated_amount": 160000.0,
                        "spent_amount": 122000.0,
                        "savings_narrative": "تطوير أنظمة الموارد البشرية والداشبورد داخلياً دون الاستعانة بشركات برمجة خارجية",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    },
                    {
                        "item_name": "بند صيانة شبكات وأجهزة البصمة",
                        "allocated_amount": 80000.0,
                        "spent_amount": 58000.0,
                        "savings_narrative": "تنفيذ الصيانة الدورية لأجهزة البصمة والربط الشبكي بواسطة مهندسي الإدارة",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            },
            {
                "general_dept_name": "السلامة والصحة المهنية وحماية",
                "fiscal_year": 2026,
                "quarter": 4,
                "allocated_amount": 95000.0,
                "items": [
                    {
                        "item_name": "بند مهمات وقاية وتدريب",
                        "allocated_amount": 95000.0,
                        "spent_amount": 76000.0,
                        "savings_narrative": "عقد الدورات التدريبية وورش السلامة داخلياً بقاعات الشركة بدلاً من القاعات الخارجية",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            },
            {
                "general_dept_name": "العمليات",
                "fiscal_year": 2026,
                "quarter": 4,
                "allocated_amount": 380000.0,
                "items": [
                    {
                        "item_name": "بند قطع غيار ومعدات تشغيل الحقول",
                        "allocated_amount": 250000.0,
                        "spent_amount": 195000.0,
                        "savings_narrative": "تصنيع الوصلات الميكانيكية محلياً وإعادة تدوير المعدات المستردة",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    },
                    {
                        "item_name": "بند إمدادات الطاقة والمولدات",
                        "allocated_amount": 130000.0,
                        "spent_amount": 99000.0,
                        "savings_narrative": "تحسين معامل القدرة الكهربائية وتقليل الفاقد الحراري بمحطات التوليد",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            },
            {
                "general_dept_name": "الشئون المالية",
                "fiscal_year": 2026,
                "quarter": 4,
                "allocated_amount": 85000.0,
                "items": [
                    {
                        "item_name": "بند مطبوعات وسجلات مالية وأرشفة",
                        "allocated_amount": 85000.0,
                        "spent_amount": 59500.0,
                        "savings_narrative": "ميكنة تقارير الموازنة والربط المباشر مع إدارات الشركة بدون نماذج ورقية",
                        "gm_approved": False,
                        "gm_approved_by": None,
                        "hse_approved": False,
                        "hse_approved_by": None,
                        "workflow_status": "NEW",
                        "cost_avoidance_amount": 0.0,
                    }
                ]
            }
        ]

        seeded_budgets = 0
        seeded_items = 0

        for entry in budget_data:
            dept_budget = db.query(DepartmentBudget).filter(
                DepartmentBudget.general_dept_name == entry["general_dept_name"],
                DepartmentBudget.fiscal_year == entry["fiscal_year"],
                DepartmentBudget.quarter == entry["quarter"]
            ).first()

            if not dept_budget:
                dept_budget = DepartmentBudget(
                    general_dept_name=entry["general_dept_name"],
                    fiscal_year=entry["fiscal_year"],
                    quarter=entry["quarter"],
                    allocated_amount=entry["allocated_amount"]
                )
                db.add(dept_budget)
                db.flush()
                seeded_budgets += 1

            for item_data in entry["items"]:
                existing_item = db.query(BudgetLineItem).filter(
                    BudgetLineItem.budget_id == dept_budget.id,
                    BudgetLineItem.item_name == item_data["item_name"]
                ).first()
                if not existing_item:
                    new_item = BudgetLineItem(
                        budget_id=dept_budget.id,
                        item_name=item_data["item_name"],
                        allocated_amount=item_data["allocated_amount"],
                        spent_amount=item_data["spent_amount"],
                        savings_narrative=item_data["savings_narrative"],
                        created_by_emp_id=7071,
                        gm_approved=item_data.get("gm_approved", False),
                        gm_approved_by=item_data.get("gm_approved_by"),
                        hse_approved=item_data.get("hse_approved", False),
                        hse_approved_by=item_data.get("hse_approved_by"),
                        workflow_status=item_data.get("workflow_status", "NEW"),
                        cost_avoidance_amount=item_data.get("cost_avoidance_amount", 0.0)
                    )
                    db.add(new_item)
                    seeded_items += 1

        db.commit()
        return {
            "seeded_budgets": seeded_budgets,
            "seeded_items": seeded_items,
            "total_users": db.query(BudgetUser).count(),
            "total_gov_configs": db.query(BudgetGovernanceConfig).count(),
            "total_lookups": db.query(SystemLookupOption).count(),
        }
    except Exception as e:
        db.rollback()
        print(f"[STANDALONE SEED ERROR] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    res = initialize_and_seed_standalone_db()
    print(f"[STANDALONE DB READY] {res}")
