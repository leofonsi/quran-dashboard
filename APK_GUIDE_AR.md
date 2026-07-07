# طريقة تحويل المشروع إلى APK

## الطريقة الأسهل: Android WebView

### 1) انشر مشروع FastAPI
يجب أن تحصل على رابط مثل:

```text
https://quran-dashboard.onrender.com
```

لا تستعمل داخل APK الرابط:

```text
http://127.0.0.1:8000
```

لأنه يعمل فقط داخل الحاسوب.

### 2) أنشئ مشروع Android Studio
اختر:

```text
Empty Views Activity
Language: Kotlin
Minimum SDK: 23
```

### 3) أضف صلاحية الإنترنت
في `AndroidManifest.xml` أضف فوق `<application>`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

### 4) كود MainActivity.kt
ضع الرابط المنشور بدل `https://YOUR-DOMAIN.com`:

```kotlin
package com.example.qurandashboard

import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this)
        setContentView(webView)
        webView.webViewClient = WebViewClient()
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.loadUrl("https://YOUR-DOMAIN.com")
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }
}
```

### 5) إنشاء APK
من Android Studio:

```text
Build > Build Bundle(s) / APK(s) > Build APK(s)
```

ستجد APK في:

```text
app/build/outputs/apk/debug/app-debug.apk
```

## طريقة ثانية: PWA
بعد نشر المشروع على HTTPS، افتح الرابط في Chrome على الهاتف ثم:

```text
Add to Home Screen / إضافة إلى الشاشة الرئيسية
```

المشروع يحتوي مسبقًا على:

```text
static/manifest.json
static/service-worker.js
```

أي أنه جاهز كتطبيق PWA.
