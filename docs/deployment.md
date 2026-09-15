# راه‌اندازی روی Oracle Always Free

این راهنما برای **یک ماشین تازهٔ Ubuntu 24.04** و حسابی است که به Pay As You Go ارتقا پیدا نکرده باشد. هزینهٔ صفر به باقی‌ماندن همهٔ منابع در سهمیه و ظرفیت قابل تخصیص Oracle وابسته است؛ اعتبار آزمایشی مبنای برنامه نیست.

## ۱. حساب، شبکه و دیسک

1. در [ثبت‌نام Oracle](https://signup.cloud.oracle.com/) با اطلاعات خودت ثبت‌نام کن و تأیید کارت را خودت انجام بده. رمز، کارت و کلید خصوصی را در چت یا مخزن قرار نده.
2. یک compartment اختصاصی به نام `motivation` در home region بساز. فقط منابع دارای نشان Always Free را انتخاب کن: `VM.Standard.A1.Flex`، ۲ OCPU، حافظهٔ ۱۲ GB، Ubuntu 24.04 ARM و boot volume برابر ۵۰ GB. اگر ظرفیت موجود نبود، ساخت محصول را به منابع پولی منتقل نکن؛ بعداً ظرفیت همان منطقه را بررسی کن.
3. شبکهٔ عمومی با IPv4 و Internet Gateway؛ دسترسی ورودی 80 و 443، و SSH فقط از IP خودت. پورت 8000 را عمومی نکن. خروجی HTTPS و DNS برای worker لازم است.
4. یک block volume تازهٔ ۱۵۰ GB در همان home region و همان availability domain بساز و با paravirtualized attachment وصل کن. boot و data در مجموع ۲۰۰ GB؛ volume اضافه، replication، منابع paid یا backup policy پیش‌فرض دیگری فعال نکن.
5. روی سرور با `lsblk -f` دیسک تازه را مشخص کن. فقط دیسک تازهٔ خالی را ext4 کن و در `/srv/motivation` mount کن؛ boot disk را فرمت نکن. UUID دیسک را در `/etc/fstab` ثبت کن. نصب‌کننده اگر این مسیر واقعاً mount نباشد متوقف می‌شود. قبل از ادامه، `findmnt /srv/motivation` و یک reboot آزمایشی انجام بده.
6. فایروال خود Ubuntu هم باید 80 و 443 را بپذیرد؛ اگر image از iptables استفاده می‌کند، قوانین را پیش از REJECT پایانی قرار بده و با ابزار همان image دائمی کن. قوانین SSH فعلی را حفظ کن.

سهمیهٔ compute و دیسک فعلی: [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm). در روز ساخت، نشان و سهمیهٔ واقعی Console را دوباره کنترل کن. ماشین کم‌استفاده ممکن است پس گرفته شود؛ پشتیبان محلی برای همین مهم است.

## ۲. انتقال پروژه و نصب

روی سرور، سورس عمومی را دریافت کن و تنظیمات خصوصی را جداگانه بساز:

```sh
git clone https://github.com/itsmohsenjalali/halekhoob.git ~/motivation
cd ~/motivation
```

نام رایگان را از IPv4 همان سرور بساز؛ مثلاً `archive.203.0.113.10.sslip.io` صرفاً نمونه است و باید IP واقعی جایگزین شود. این نام به سرویس DNS عمومی sslip.io وابسته است. ابتدا تطبیق DNS با IP سرور را بررسی کن. خرید دامنه لازم نیست.

روی سرور:

```sh
cd ~/motivation
sudo bash deploy/bootstrap.sh archive.YOUR_PUBLIC_IP.sslip.io
```

نصب‌کننده Python/FFmpeg/Nginx و Node رسمی با بررسی SHA-256 را نصب می‌کند، محیط تولید و secret تصادفی می‌سازد، migration و collectstatic و بررسی امنیت Django را اجرا می‌کند، سرویس‌ها را نصب می‌کند و با Certbot برای نام انتخابی HTTPS می‌گیرد. آخر کار نام کاربری و رمز شخصی را از ترمینال می‌پرسد. تمدید خودکار Certbot را با `sudo certbot renew --dry-run` بررسی کن.

فایل داده در `/srv/motivation/data`، کد در `/opt/motivation/app` و تنظیمات خصوصی در `/etc/motivation/app.env` است. فایل secret را جدا و امن روی دستگاه خودت نگه دار. Nginx فقط به 127.0.0.1:8000 وصل می‌شود و هدرهای پراکسی را بازنویسی می‌کند. هیچ `alias` عمومی برای media تعریف نکن.

```sh
sudo systemctl status motivation-web motivation-worker
sudo /opt/motivation/app/deploy/manage.sh check --deploy --fail-level WARNING
sudo certbot renew --dry-run
```

## ۳. آزمون ۱۰ لینک روی خود سرور

یک `links.txt` خصوصی با دقیقاً ۱۰ لینک عمومی و مجزا بساز: ویدیو و Shorts یوتیوب و Reel/پست تک‌ویدیویی اینستاگرام. سپس در پوشهٔ پروژه، با محیط Python نصب‌شده و یک مسیر **تازه** روی دیسک داده اجرا کن:

```sh
sudo install -d -o motivation -g motivation -m 0700 /srv/motivation/smoke
sudo -u motivation env PATH=/opt/motivation/venv/bin:/opt/motivation/node/bin:/usr/bin:/bin /opt/motivation/venv/bin/python scripts/smoke_downloads.py /path/to/links.txt --data-dir /srv/motivation/smoke/run-01 --report /srv/motivation/smoke/report-01.json
```

این ابزار از پایگاه دادهٔ جدا استفاده می‌کند و آرشیو اصلی را تغییر نمی‌دهد. موفقیت واقعی هر ۱۰ ورودی و پخش MP4 روی موبایل را بررسی کن. سپس یک لینک از هر پلتفرم از طریق خود سایت و worker محدودشده با systemd هم امتحان کن؛ محدودیت شبکهٔ سرویس نیز باید در آزمون لحاظ شود. در صورت شکست، کد خطا و علت را بررسی کن؛ فایل آماده فرض نشود و لینک تنها جایگزین آرشیو فایل نشود.

برای بررسی جلوگیری از دسترسی داخلی، تنظیم `IPAddressDeny` سرویس worker و پشتیبانی BPF هسته را کنترل کن. guard داخل Python هم DNS و آدرس خصوصی را مسدود می‌کند؛ مسیر واقعی محدودسازی systemd باید روی Ubuntu آزموده شود.

## ۴. پشتیبان روزانه در سهمیهٔ پنج نسخه

هدف: یک boot backup و حداکثر چهار data backup. چون امکان نگه‌داشتن نسخهٔ ششم نداریم، هنگام پرشدن سهمیه قدیمی‌ترین data backup مدیریت‌شده پیش از ساخت نسخهٔ جدید حذف می‌شود. اگر ساخت نسخهٔ جدید شکست بخورد، سه نسخهٔ قبلی داده باقی می‌ماند. اسکریپت backupهای نامرتبط را حذف نمی‌کند.

1. یک dynamic group محدود به OCID همین instance بساز. برای instance principal، مجوز `inspect compartments` و `inspect tenancies` در tenancy، `read volume-backups` و `read boot-volume-backups` در tenancy و `manage volume-family` فقط در compartment `motivation` بده. inventory باید بتواند همهٔ compartmentها را ببیند؛ خطای مجوز باعث توقف می‌شود. این مجوز فقط برای سرویس backup است؛ worker به metadata خصوصی دسترسی ندارد.
2. CLI عملیات را در محیط جدا نصب کن:

```sh
sudo python3.12 -m venv /opt/motivation/ops
sudo /opt/motivation/ops/bin/pip install --no-cache-dir 'oci-cli==3.92.1'
sudo install -m 0600 deploy/backup.env.example /etc/motivation/backup.env
sudoedit /etc/motivation/backup.env
```

OCIDهای tenancy، compartment، boot volume، data volume و home region واقعی را وارد کن. این فایل کلید خصوصی ندارد؛ احراز هویت instance principal است.

3. ابتدا فقط inventory و برنامهٔ rotation را ببین:

```sh
sudo bash -c 'set -a; source /etc/motivation/backup.env; set +a; python3 /opt/motivation/app/deploy/oci_backup.py'
```

4. پس از درست بودن شناسه‌ها و سهمیه، سرویس و timer را نصب و اولین backup را اجرا کن:

```sh
sudo install -m 0644 deploy/motivation-backup.service deploy/motivation-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start motivation-backup.service
sudo systemctl enable --now motivation-backup.timer
sudo journalctl -u motivation-backup.service -n 60 --no-pager
```

هر روز ساعت ۴ صبح به وقت سرور اجرا می‌شود. سایت و worker هنگام snapshot کوتاه‌مدت متوقف و سپس دوباره فعال می‌شوند تا SQLite و فایل‌ها سازگار بمانند. timeout ممکن است این توقف را طولانی کند؛ وضعیت سرویس و `backup-status.json` را بررسی کن. پشتیبان ابری بعد از ساخت باید یک‌بار روی volume بازیابی‌شده آزموده شود؛ برای آزمایش volume اضافه از سهمیهٔ ۲۰۰ GB عبور نکن.

## ۵. خروجی هفتگی روی کامپیوتر خودت

```sh
bash deploy/export-weekly.sh ubuntu@YOUR_SERVER /path/to/private-backups
```

اسکریپت یک snapshot سازگار را مستقیماً از طریق SSH به کامپیوترت stream می‌کند؛ نسخهٔ دوم از ویدیوها روی دیسک ۱۵۰ GB سرور ساخته نمی‌شود. پس از پایان انتقال، checksum همهٔ فایل‌ها و سلامت SQLite بررسی می‌شود و فایل `.partial` به نام نهایی تغییر می‌کند. هنگام گرفتن snapshot، نوشتن در آرشیو منتظر می‌ماند ولی تماشای ویدیوهای موجود ادامه دارد. برای آرشیو بزرگ این کار زمان می‌برد. فضای کافی برای نسخهٔ کامل روی کامپیوترت لازم است؛ نسخه‌های قبلی خودکار حذف نمی‌شوند.

برای زمان‌بندی هفتگی از launchd در macOS یا cron روی کامپیوتر خودت استفاده کن؛ کامپیوتر باید روشن و SSH بدون درخواست تعاملی آماده باشد. زمان‌بندی محلی و مجوز sudo خودکار بدون تنظیم کاربر فعال نمی‌شود. snapshot شامل هش رمز و sessionهاست؛ آن را خصوصی نگه دار.

بازیابی آزمایشی در یک مسیر تازه، بدون دست‌زدن به آرشیو جاری:

```sh
DJANGO_DEBUG=1 .venv/bin/python manage.py restore_archive /path/to/archive.tar /path/to/new-restored-data
```

checksum همهٔ فایل‌ها و سلامت SQLite بررسی می‌شود. برای بازیابی اصلی، سرویس‌ها را متوقف کن، مسیر `DATA_DIR` و مالکیت فایل‌ها را به نسخهٔ تأییدشده تغییر بده و سپس سرویس‌ها را بالا بیاور. مسیر موجود هرگز توسط restore بازنویسی نمی‌شود.

## معیار تحویل روی سرور

- HTTPS معتبر و تمدید آزمایشی موفق؛ مسیرهای فایل و وضعیت بدون ورود قابل مشاهده نباشند.
- ۱۰ لینک واقعی با نتیجهٔ ثبت‌شده، تصویر و صدا و seek سالم روی موبایل.
- قطع worker هنگام دانلود و ادامهٔ صف پس از راه‌اندازی؛ افزودن رکورد تکراری فایل جدید نسازد.
- یک backup روزانه و یک export محلی ساخته و بازیابی آزمایشی شده باشد.
- سهمیهٔ compute، دیسک، backup و ترافیک در Console داخل Always Free بماند.
- پس از افزودن ۲۰ ویدیوی شخصی، یک هفته استفاده و سنجش رسیدن به پخش در کمتر از ۱۵ ثانیه.
