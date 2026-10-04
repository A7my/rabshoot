# Privacy / الخصوصية

## English

**Where your data lives.** Everything stays on your computer. RabShoot has no server.

- Accounts and settings: `~/.config/rabshoot` (Linux) or `%APPDATA%\RabShoot` (Windows).
- Passwords and tokens: the system keychain (Windows Credential Manager / Linux Secret Service).
  If no keychain is available, a private file readable only by your user; Settings shows which one
  is in use.
- Report history and copies of sent emails: `~/.local/share/rabshoot` (Linux) or the same Windows folder.

**What leaves your computer, and to whom.**

| Destination | What is sent |
|---|---|
| GitLab / GitHub | Read-only API requests with your token |
| Slack | Read-only API requests for the conversations you picked |
| Your AI provider (Google Gemini by default) | Code diffs of the day and the picked Slack messages, to write the summary |
| Your email provider | The finished report, sent from your account |

**Protections before anything reaches the AI.**

- Lock files, `.env` files, keys, certificates, binaries, and generated or minified files are never sent.
- Values that look like secrets (tokens, passwords, keys) are masked in the diffs.
- Only the day's changes are sent, within a size limit you can change per report.

**Free AI keys.** Google's free Gemini tier may use submitted content to improve Google products.
For company code, use a paid key or check your company's policy first.

**Removing everything.** Delete the account in *Accounts* (this removes its token from the keychain),
or remove the folders above after uninstalling.

## العربية

**أين تُحفظ بياناتك؟** كل شيء يبقى على جهازك. RabShoot ليس له أي خادم.

- الحسابات والإعدادات: `~/.config/rabshoot` على لينكس أو `%APPDATA%\RabShoot` على ويندوز.
- كلمات المرور والتوكنات: في خزنة النظام الآمنة (Windows Credential Manager / Linux Secret Service).
  لو الخزنة غير متاحة، تُحفظ في ملف خاص لا يقرؤه غير مستخدمك. صفحة الإعدادات توضح أيهما مستخدم.
- سجل التقارير ونسخ الإيميلات المرسلة: `~/.local/share/rabshoot` على لينكس، أو نفس مجلد ويندوز.

**ما الذي يخرج من جهازك، ولمن؟**

| الجهة | ما يُرسل لها |
|---|---|
| GitLab / GitHub | طلبات قراءة فقط باستخدام التوكن الخاص بك |
| Slack | طلبات قراءة فقط للمحادثات التي اخترتها |
| مزوّد الذكاء الاصطناعي (Google Gemini افتراضيًا) | تغييرات الكود في اليوم ورسائل Slack المختارة، لكتابة الملخص |
| مزوّد بريدك | التقرير النهائي، ويُرسل من حسابك أنت |

**حماية قبل الإرسال للذكاء الاصطناعي.**

- لا تُرسل أبدًا ملفات الـ lock، ولا ملفات `.env`، ولا المفاتيح والشهادات والملفات الثنائية والملفات المولّدة.
- أي قيمة تشبه سرًا (توكن أو كلمة مرور أو مفتاح) تُخفى من التغييرات.
- تُرسل تغييرات اليوم فقط، في حدود حجم يمكنك تغييره لكل تقرير.

**مفاتيح AI المجانية.** الخطة المجانية من Gemini قد تستخدم المحتوى المرسل لتحسين منتجات Google.
لو الكود خاص بشركة، استخدم مفتاحًا مدفوعًا أو راجع سياسة الشركة أولًا.

**لحذف كل شيء.** احذف الحساب من صفحة *الحسابات* (وهذا يحذف التوكن من الخزنة)، أو احذف المجلدات
المذكورة بعد إلغاء تثبيت البرنامج.
