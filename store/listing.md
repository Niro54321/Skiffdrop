# Skiffdrop — Microsoft Store listing

Copy each field into Partner Center › Store listings. Category: **Utilities & tools › File managers**.
Price: **Free**. Screenshots: `screenshots/<language>/` (1920 × 1080, three per language, already captioned).

Store logos (`logos/`, the same for every language):

| Partner Center field | File |
|---|---|
| 1:1 App tile icon (300 × 300) | `app-tile-icon-300.png` |
| 1:1 Box art (1080 × 1080 or 2160 × 2160) | `box-art-2160.png` (or `box-art-1080.png`) |
| 2:3 Poster art (720 × 1080 or 1440 × 2160) | `poster-art-1440x2160.png` (or `poster-art-720x1080.png`) |
| 16:9 Hero image (Store display images, optional) | `hero-3840x2160.png` (or `hero-1920x1080.png`) |

Shared fields (all languages):

- **Product name:** Skiffdrop
- **Copyright:** © 2026 fogamas (Niro54321)
- **Privacy policy URL:** https://github.com/Niro54321/Skiffdrop/blob/main/PRIVACY.md
- **Website:** https://github.com/Niro54321/Skiffdrop
- **Support contact:** https://github.com/Niro54321/Skiffdrop/issues
- **Package:** `Skiffdrop-1.0.0.0.msix` (identity `fogamas.Skiffdrop`, publisher `CN=127AB4A2-386C-4D9F-973A-2A5242F53E4D`)

**Submission options › Restricted capabilities (why runFullTrust):**

> Skiffdrop is a desktop (Win32) app written with Qt, packaged as MSIX. It needs runFullTrust to run its desktop executable, show a tray icon and run a small web server on the local network that the user's own phone opens to send and receive files. It declares a firewall rule for private networks only (TCP 7340–7359). It does not access other apps' data and never connects to the internet.

**Notes for certification:**

> Skiffdrop moves files between a phone and this PC over the local network. To test without a phone: start Skiffdrop, open Microsoft Edge on the same PC and go to http://127.0.0.1:7340, type the 6-digit code shown in Skiffdrop, click Connect, then click Allow on the card that appears at the bottom right of the screen. The page can now send files (they appear in Downloads\Skiffdrop and in the Files list) and receive files dropped on the Skiffdrop window. No account or test login is needed. The app makes no internet connections.

**Age rating (IARC questionnaire):** category *Utility / Productivity*; answer **No** to every question (no violence, no communication with other users: it only connects the user's own devices on their own network, no location sharing, no purchases). Expected rating: 3+ / Everyone.

**Screenshot captions** (optional, Partner Center › Screenshots › caption): use the title written on each picture.

---

## English (en-us)

**Short description**

Send photos, videos and files between your phone and your PC over your own Wi-Fi. Scan a QR code: nothing to install on the phone, no account, no cloud.

**Description**

Skiffdrop moves files between your phone and your Windows PC without sending them to yourself on WhatsApp, Discord or email.

Open Skiffdrop on the PC and scan its QR code with the iPhone or Android camera. The phone opens Skiffdrop in Safari or Chrome with the code already filled in: tap Connect, click Allow on the PC, and you're paired. Nothing is installed on the phone.

From the phone, pick photos, videos or any file, as many and as large as you like, and watch them arrive with their speed. Big files go in pieces, so a dropped connection picks up where it stopped. They're saved in Downloads\Skiffdrop.

From the PC, drag files or whole folders onto the window. They show up on the phone with previews, a Save button and Save all as a zip. Text and links go both ways, and text from the phone lands on your clipboard.

Messages and Files are two lists on the PC that keep everything you sent and received, even after a restart.

Everything stays on your own network: no account, no cloud, no ads, no tracking. Each new phone needs your OK on the PC, you can add a PIN, and the firewall rule covers private networks only.

Skiffdrop speaks English, Arabic, Spanish, French, Japanese and Chinese, follows Windows' dark or light mode, and is free and open source (MIT).

**Product features**

- Send photos, videos and any file from iPhone or Android to your PC
- Send files and whole folders from your PC to your phone
- Nothing to install on the phone: scan a QR code, tap Connect
- Any size: big files go in pieces and resume after a dropped connection
- Text and links both ways, straight to the clipboard
- Messages and Files lists that stay after a restart
- Stays on your own Wi-Fi: no account, no cloud, no tracking
- Your OK for every new phone, optional PIN, private-network firewall rule
- Dark and light, following Windows
- English, Arabic, Spanish, French, Japanese and Chinese
- Free and open source (MIT)

**Search terms:** file transfer, phone to pc, iphone to pc, android to pc, share files, send photos, wifi transfer

**What's new in this version:** First release on the Microsoft Store.

---

## العربية (ar)

**وصف مختصر**

انقل الصور والفيديو والملفات بين هاتفك والكمبيوتر عبر شبكة الواي فاي الخاصة بك. امسح رمز QR فقط: لا شيء يُثبَّت على الهاتف، بلا حساب وبلا سحابة.

**الوصف**

ينقل Skiffdrop الملفات بين هاتفك وكمبيوتر Windows دون أن ترسلها لنفسك على واتساب أو ديسكورد أو البريد.

افتح Skiffdrop على الكمبيوتر وامسح رمز QR بكاميرا الآيفون أو الأندرويد. يفتح الهاتف Skiffdrop في Safari أو Chrome والرمز معبّأ تلقائياً: اضغط «اتصال»، ثم «سماح» على الكمبيوتر، وتم الاقتران. لا شيء يُثبَّت على الهاتف.

من الهاتف اختر صوراً أو فيديو أو أي ملف، بأي عدد وأي حجم، وتابع وصولها مع سرعة النقل. الملفات الكبيرة تُرسل على أجزاء، فإذا انقطع الاتصال يكمل من حيث توقف. وتُحفظ في مجلد Downloads\Skiffdrop.

من الكمبيوتر اسحب الملفات أو المجلدات كاملة إلى النافذة. تظهر على الهاتف مع معاينة وزر «حفظ» وخيار «حفظ الكل» كملف zip. والنصوص والروابط تنتقل في الاتجاهين، والنص القادم من الهاتف يُنسخ إلى الحافظة.

على الكمبيوتر خانتان: «الرسائل» و«الملفات»، تحفظان كل ما أرسلته واستلمته حتى بعد إعادة التشغيل.

كل شيء يبقى داخل شبكتك: بلا حساب، بلا سحابة، بلا إعلانات، بلا تتبع. كل هاتف جديد يحتاج موافقتك على الكمبيوتر، ويمكنك إضافة رقم سري، وقاعدة جدار الحماية للشبكات الخاصة فقط.

يدعم Skiffdrop العربية والإنجليزية والإسبانية والفرنسية واليابانية والصينية، ويتبع الوضع الداكن أو الفاتح في Windows، وهو مجاني ومفتوح المصدر (MIT).

**المميزات**

- أرسل الصور والفيديو وأي ملف من الآيفون أو الأندرويد إلى الكمبيوتر
- أرسل الملفات والمجلدات كاملة من الكمبيوتر إلى الهاتف
- لا شيء يُثبَّت على الهاتف: امسح رمز QR واضغط «اتصال»
- أي حجم: الملفات الكبيرة تُرسل على أجزاء وتكمل بعد انقطاع الاتصال
- النصوص والروابط في الاتجاهين، مباشرة إلى الحافظة
- خانتا «الرسائل» و«الملفات» تبقيان بعد إعادة التشغيل
- يبقى داخل شبكتك: بلا حساب، بلا سحابة، بلا تتبع
- موافقتك لكل هاتف جديد، ورقم سري اختياري، وجدار حماية للشبكات الخاصة فقط
- داكن وفاتح، مثل Windows
- العربية والإنجليزية والإسبانية والفرنسية واليابانية والصينية
- مجاني ومفتوح المصدر (MIT)

**كلمات البحث:** نقل الملفات, من الهاتف للكمبيوتر, ايفون للكمبيوتر, اندرويد للكمبيوتر, مشاركة الملفات, نقل الصور, واي فاي

**الجديد في هذا الإصدار:** أول إصدار على متجر مايكروسوفت.

---

## Español (es)

**Descripción breve**

Envía fotos, vídeos y archivos entre tu teléfono y tu PC por tu propia red Wi-Fi. Escanea un código QR: nada que instalar en el teléfono, sin cuenta y sin nube.

**Descripción**

Skiffdrop mueve archivos entre tu teléfono y tu PC con Windows sin tener que enviártelos por WhatsApp, Discord o correo.

Abre Skiffdrop en el PC y escanea su código QR con la cámara del iPhone o Android. El teléfono abre Skiffdrop en Safari o Chrome con el código ya escrito: toca Conectar, pulsa Permitir en el PC y listo. No se instala nada en el teléfono.

Desde el teléfono, elige fotos, vídeos o cualquier archivo, tantos y tan grandes como quieras, y mira cómo llegan con su velocidad. Los archivos grandes van por partes, así que si se corta la conexión continúa donde se quedó. Se guardan en Descargas\Skiffdrop.

Desde el PC, arrastra archivos o carpetas enteras a la ventana. Aparecen en el teléfono con vista previa, un botón Guardar y Guardar todo en zip. Los textos y enlaces van en ambos sentidos, y el texto del teléfono llega al portapapeles.

Mensajes y Archivos son dos listas en el PC que guardan todo lo que enviaste y recibiste, incluso después de reiniciar.

Todo se queda en tu red: sin cuenta, sin nube, sin anuncios, sin rastreo. Cada teléfono nuevo necesita tu permiso en el PC, puedes añadir un PIN y la regla del firewall solo cubre redes privadas.

Skiffdrop está en inglés, árabe, español, francés, japonés y chino, sigue el modo oscuro o claro de Windows y es gratuito y de código abierto (MIT).

**Características del producto**

- Envía fotos, vídeos y cualquier archivo del iPhone o Android al PC
- Envía archivos y carpetas enteras del PC al teléfono
- Nada que instalar en el teléfono: escanea un código QR y toca Conectar
- Cualquier tamaño: los archivos grandes van por partes y se reanudan si se corta
- Textos y enlaces en ambos sentidos, directos al portapapeles
- Listas de Mensajes y Archivos que siguen ahí tras reiniciar
- Se queda en tu Wi-Fi: sin cuenta, sin nube, sin rastreo
- Tu permiso para cada teléfono nuevo, PIN opcional y firewall solo en redes privadas
- Modo oscuro y claro, como Windows
- Inglés, árabe, español, francés, japonés y chino
- Gratuito y de código abierto (MIT)

**Términos de búsqueda:** transferir archivos, del móvil al PC, iPhone a PC, Android a PC, compartir archivos, enviar fotos, Wi-Fi

**Novedades de esta versión:** Primera versión en Microsoft Store.

---

## Français (fr)

**Description courte**

Envoyez photos, vidéos et fichiers entre votre téléphone et votre PC sur votre propre Wi-Fi. Scannez un QR code : rien à installer sur le téléphone, sans compte ni cloud.

**Description**

Skiffdrop transfère des fichiers entre votre téléphone et votre PC Windows sans vous les envoyer par WhatsApp, Discord ou e-mail.

Ouvrez Skiffdrop sur le PC et scannez son QR code avec l’appareil photo de l’iPhone ou d’Android. Le téléphone ouvre Skiffdrop dans Safari ou Chrome avec le code déjà rempli : touchez Connecter, cliquez sur Autoriser sur le PC, et c’est associé. Rien n’est installé sur le téléphone.

Depuis le téléphone, choisissez photos, vidéos ou n’importe quel fichier, autant et aussi gros que vous voulez, et suivez leur arrivée avec la vitesse. Les gros fichiers partent en morceaux : si la connexion coupe, l’envoi reprend là où il s’est arrêté. Ils sont enregistrés dans Téléchargements\Skiffdrop.

Depuis le PC, glissez des fichiers ou des dossiers entiers sur la fenêtre. Ils apparaissent sur le téléphone avec un aperçu, un bouton Enregistrer et Tout enregistrer en zip. Textes et liens passent dans les deux sens, et le texte du téléphone arrive dans le presse-papiers.

Messages et Fichiers sont deux listes sur le PC qui gardent tout ce que vous avez envoyé et reçu, même après un redémarrage.

Tout reste sur votre réseau : sans compte, sans cloud, sans publicité, sans pistage. Chaque nouveau téléphone demande votre accord sur le PC, vous pouvez ajouter un code PIN, et la règle du pare-feu ne couvre que les réseaux privés.

Skiffdrop parle anglais, arabe, espagnol, français, japonais et chinois, suit le mode sombre ou clair de Windows, et il est gratuit et open source (MIT).

**Fonctionnalités du produit**

- Envoyez photos, vidéos et tout fichier de l’iPhone ou d’Android vers le PC
- Envoyez des fichiers et des dossiers entiers du PC vers le téléphone
- Rien à installer sur le téléphone : scannez un QR code, touchez Connecter
- Toutes tailles : les gros fichiers partent en morceaux et reprennent après une coupure
- Textes et liens dans les deux sens, directement dans le presse-papiers
- Listes Messages et Fichiers conservées après un redémarrage
- Reste sur votre Wi-Fi : sans compte, sans cloud, sans pistage
- Votre accord pour chaque nouveau téléphone, code PIN facultatif, pare-feu réseaux privés uniquement
- Sombre et clair, comme Windows
- Anglais, arabe, espagnol, français, japonais et chinois
- Gratuit et open source (MIT)

**Termes de recherche :** transfert de fichiers, téléphone vers PC, iPhone vers PC, Android vers PC, partager des fichiers, envoyer des photos, Wi-Fi

**Nouveautés de cette version :** Première version sur le Microsoft Store.

---

## 日本語 (ja)

**簡単な説明**

自分の Wi-Fi で、スマホと PC の間で写真・ビデオ・ファイルを送受信。QR コードをスキャンするだけで、スマホへのインストールもアカウントもクラウドも不要です。

**説明**

Skiffdrop は、スマホと Windows PC の間でファイルをやり取りするアプリです。WhatsApp や Discord、メールで自分宛てに送る必要はもうありません。

PC で Skiffdrop を開き、iPhone や Android のカメラで QR コードをスキャンします。スマホの Safari や Chrome で Skiffdrop がコード入力済みの状態で開くので、「接続」をタップして PC で「許可」をクリックすればペアリング完了。スマホには何もインストールしません。

スマホからは、写真やビデオ、あらゆるファイルを好きなだけ、どんなサイズでも選べます。届く様子と速度も表示されます。大きなファイルは分割して送るので、接続が切れても続きから再開します。保存先はダウンロード\Skiffdrop です。

PC からは、ファイルやフォルダーをウィンドウにドラッグするだけ。スマホにはプレビュー、「保存」ボタン、zip での「すべて保存」が表示されます。テキストやリンクも双方向に送れ、スマホからのテキストはクリップボードに入ります。

PC の「メッセージ」と「ファイル」の 2 つの一覧には、送受信したものがすべて残り、再起動後も消えません。

すべて自分のネットワーク内で完結：アカウント、クラウド、広告、トラッキングはありません。新しいスマホは PC での許可が必要で、PIN も設定でき、ファイアウォールのルールはプライベート ネットワークだけに適用されます。

日本語、英語、アラビア語、スペイン語、フランス語、中国語に対応。Windows のダーク／ライトモードに合わせて表示され、無料のオープンソース（MIT）です。

**製品の特長**

- iPhone や Android から PC へ写真・ビデオ・あらゆるファイルを送信
- PC からスマホへファイルやフォルダーごと送信
- スマホへのインストール不要：QR コードをスキャンして「接続」をタップ
- サイズ無制限：大きなファイルは分割送信、切断されても再開
- テキストやリンクを双方向に、そのままクリップボードへ
- 再起動後も残る「メッセージ」と「ファイル」の一覧
- 自分の Wi-Fi 内で完結：アカウント・クラウド・トラッキングなし
- 新しいスマホごとに許可、PIN（任意）、プライベート ネットワーク限定のファイアウォール
- Windows に合わせたダーク／ライト
- 日本語、英語、アラビア語、スペイン語、フランス語、中国語
- 無料のオープンソース（MIT）

**検索語句:** ファイル転送, スマホ PC 転送, iPhone PC 転送, Android PC 転送, ファイル共有, 写真 転送, Wi-Fi 転送

**このバージョンの新機能:** Microsoft Store での最初のリリースです。

---

## 中文（简体）(zh-cn)

**简短说明**

通过你自己的 Wi-Fi，在手机和电脑之间传送照片、视频和文件。扫一下二维码即可：手机无需安装，无需账户，不经过云端。

**说明**

Skiffdrop 让你在手机和 Windows 电脑之间传文件，不用再通过 WhatsApp、Discord 或邮件发给自己。

在电脑上打开 Skiffdrop，用 iPhone 或安卓手机的相机扫描二维码。手机会在 Safari 或 Chrome 中打开 Skiffdrop，代码已自动填好：点按“连接”，再在电脑上点击“允许”，即可配对。手机上无需安装任何东西。

在手机上，选择照片、视频或任何文件，数量和大小不限，并可看到传输进度和速度。大文件分段发送，连接中断后会从断点继续。文件保存在“下载\Skiffdrop”。

在电脑上，把文件或整个文件夹拖到窗口中。手机上会显示预览、“保存”按钮，以及打包为 zip 的“全部保存”。文字和链接可以双向发送，手机发来的文字会直接放到剪贴板。

电脑上的“消息”和“文件”两个列表会保存你发送和接收的所有内容，重启后依然都在。

一切都留在你自己的网络中：无需账户，不经过云端，没有广告，没有跟踪。每部新手机都需要你在电脑上允许，你还可以设置 PIN，防火墙规则只适用于专用网络。

Skiffdrop 支持中文、英语、阿拉伯语、西班牙语、法语和日语，跟随 Windows 的深色或浅色模式，免费且开源（MIT）。

**产品功能**

- 从 iPhone 或安卓手机向电脑发送照片、视频和任何文件
- 从电脑向手机发送文件和整个文件夹
- 手机无需安装：扫描二维码，点按“连接”
- 不限大小：大文件分段发送，断线后可续传
- 文字和链接双向发送，直达剪贴板
- “消息”和“文件”列表重启后依然保留
- 只在你的 Wi-Fi 中传输：无需账户、不经云端、没有跟踪
- 每部新手机需你允许，可选 PIN，防火墙仅限专用网络
- 深色和浅色，跟随 Windows
- 中文、英语、阿拉伯语、西班牙语、法语和日语
- 免费开源（MIT）

**搜索词:** 文件传输, 手机传电脑, iPhone传电脑, 安卓传电脑, 文件共享, 传照片, 局域网传输

**此版本的新增功能:** 首次在 Microsoft Store 发布。
