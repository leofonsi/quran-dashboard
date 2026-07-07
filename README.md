# تطبيق متابعة حفظ القرآن الكريم

نسخة عربية RTL جاهزة للهاتف ومهيأة للتحويل إلى APK.

## المميزات
- واجهة عربية كاملة من اليمين إلى اليسار.
- Dashboard تفاعلي مع KPIs ورسوم بيانية.
- إدارة الطلاب.
- تسجيل التقييمات اليومية: السورة، الآيات، الصفحات، الأخطاء، الحضور، المراجعة، النقطة.
- أسماء سور القرآن كاملة بالعربية.
- وضع ليلي ونهاري.
- تصميم متوافق مع الهاتف.
- PWA: ملفات manifest و service worker جاهزة.
- تصدير تقرير CSV من `/report`.

## التشغيل المحلي

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
python -m uvicorn app:app --reload
```

افتح:

```text
http://127.0.0.1:8000
```

## النشر على الإنترنت

على Render أو VPS استعمل:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

## تحويله إلى APK

بعد النشر، استعمل رابط الموقع داخل Android WebView أو TWA.
راجع ملف:

```text
APK_GUIDE_AR.md
```
