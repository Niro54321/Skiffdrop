"""Composes the Microsoft Store screenshots (1920 x 1080), three per language, from
renders of the PC window (dev/shot.py) and captures of the phone page.

    .venv\\Scripts\\python.exe store\\screenshots.py <work-dir> <out-dir>

<work-dir> holds win-<lang>-dark.png, win-<lang>-light.png, pair-<lang>.jpg,
home-<lang>-dark.jpg and home-<lang>-light.jpg for en, ar, es, fr, ja, zh.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Windows itself draws the text (DirectWrite), so Japanese, Chinese and Arabic get their real fonts

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QTextOption  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from skiffdrop import theme as T  # noqa: E402
from skiffdrop.ui import load_fonts  # noqa: E402

load_fonts()
W, H = 1920, 1080
STORE_CODE = {"en": "en-us", "ar": "ar", "es": "es", "fr": "fr", "ja": "ja", "zh": "zh-cn"}

CAPTIONS = {
    "en": [("Phone ⇄ PC, over your own Wi-Fi",
            "Photos, videos and any file, both ways. Nothing goes to the internet."),
           ("Scan. Tap Connect. Done.",
            "Nothing to install on iPhone or Android: the camera opens Skiffdrop in the browser."),
           ("Dark or light, in six languages",
            "Messages and files stay listed on your PC, even after a restart.")],
    "ar": [("الهاتف ⇄ الكمبيوتر عبر شبكتك",
            "صور وفيديو وأي ملف، في الاتجاهين. لا شيء يذهب إلى الإنترنت."),
           ("امسح، اضغط اتصال، وانتهى.",
            "لا شيء يُثبَّت على آيفون أو أندرويد: الكاميرا تفتح Skiffdrop في المتصفح."),
           ("داكن أو فاتح، بست لغات",
            "الرسائل والملفات تبقى محفوظة على الكمبيوتر، حتى بعد إعادة التشغيل.")],
    "es": [("Teléfono ⇄ PC, por tu propia Wi-Fi",
            "Fotos, vídeos y cualquier archivo, en ambos sentidos. Nada va a internet."),
           ("Escanea. Toca Conectar. Listo.",
            "Nada que instalar en iPhone ni Android: la cámara abre Skiffdrop en el navegador."),
           ("Oscuro o claro, en seis idiomas",
            "Los mensajes y archivos quedan en tu PC, incluso después de reiniciar.")],
    "fr": [("Téléphone ⇄ PC, sur votre propre Wi-Fi",
            "Photos, vidéos et tout fichier, dans les deux sens. Rien ne passe par Internet."),
           ("Scannez. Touchez Connecter. C’est tout.",
            "Rien à installer sur iPhone ou Android : l’appareil photo ouvre Skiffdrop dans le navigateur."),
           ("Sombre ou clair, en six langues",
            "Les messages et fichiers restent listés sur votre PC, même après un redémarrage.")],
    "ja": [("自分の Wi-Fi でスマホ ⇄ PC",
            "写真、ビデオ、あらゆるファイルを双方向に。インターネットには何も送りません。"),
           ("スキャンして「接続」をタップするだけ",
            "iPhone にも Android にもインストール不要。カメラでブラウザから Skiffdrop が開きます。"),
           ("ダークもライトも、6 か国語で",
            "メッセージとファイルの履歴は PC に残り、再起動後も消えません。")],
    "zh": [("通过你自己的 Wi-Fi，手机 ⇄ 电脑",
            "照片、视频和任何文件，双向传输。不经过互联网。"),
           ("扫码，点“连接”，完成",
            "iPhone 和安卓都无需安装：相机直接在浏览器中打开 Skiffdrop。"),
           ("深色或浅色，支持六种语言",
            "消息和文件记录保存在电脑上，重启后依然都在。")],
}


def families(stack: str) -> list[str]:
    return [f.strip().strip("'") for f in stack.split(",")]


def text_block(p: QPainter, lang: str, title: str, sub: str, x: float, width: float, dark: bool) -> None:
    rtl = lang == "ar"
    tf = QFont()
    tf.setFamilies(families(T.display_family(lang)))
    tf.setPixelSize(T.display_size(lang, 72))
    if lang in T.SCRIPT_DISPLAY:
        tf.setWeight(QFont.Weight.DemiBold)
    sf = QFont()
    sf.setFamilies(families(T.ui_family(lang)))
    sf.setPixelSize(28)
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapMode.WordWrap)
    opt.setAlignment(Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
    opt.setTextDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)
    p.setFont(tf)
    t_rect = p.boundingRect(QRectF(x, 0, width, H), title, opt)
    p.setFont(sf)
    s_rect = p.boundingRect(QRectF(x, 0, width, H), sub, opt)
    gap = 28
    total = t_rect.height() + gap + s_rect.height() + 64
    y = (H - total) / 2
    # the brand's small brass rule above the words
    rule = QPen(QColor(T.BRASS), 4)
    rule.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(rule)
    rx = x + width - 56 if rtl else x
    p.drawLine(int(rx), int(y), int(rx + 56), int(y))
    y += 40
    p.setFont(tf)
    p.setPen(QColor(T.IVORY if dark else T.INK))
    p.drawText(QRectF(x, y, width, t_rect.height()), title, opt)
    y += t_rect.height() + gap
    p.setFont(sf)
    p.setPen(QColor(244, 239, 230, 175) if dark else QColor(10, 15, 26, 170))
    p.drawText(QRectF(x, y, width, s_rect.height()), sub, opt)


def framed(p: QPainter, img: QImage, r: QRectF, radius: float, dark: bool) -> None:
    """A screenshot with rounded corners, a hairline and a soft neutral shadow."""
    for i in range(14, 0, -2):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 7 if dark else 5))
        p.drawRoundedRect(r.adjusted(-i, -i + 10, i, i + 10), radius + i, radius + i)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.save()
    p.setClipPath(path)
    p.drawImage(r, img)
    p.restore()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(244, 239, 230, 40) if dark else QColor(10, 15, 26, 40), 1.5))
    p.drawRoundedRect(r, radius, radius)


def place(x: float, w: float, rtl: bool) -> float:
    return W - x - w if rtl else x


def compose(work: Path, out: Path, lang: str) -> None:
    rtl = lang == "ar"
    caps = CAPTIONS[lang]
    folder = out / STORE_CODE[lang]
    folder.mkdir(parents=True, exist_ok=True)

    # 1. the PC window
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor(T.INK))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    win = QImage(str(work / f"win-{lang}-dark.png"))
    k = 860 / win.height()
    ww, wh = win.width() * k, win.height() * k
    framed(p, win, QRectF(place(W - 90 - ww, ww, rtl), (H - wh) / 2, ww, wh), 14, True)
    text_block(p, lang, *caps[0], place(100, 600, rtl), 600, True)
    p.end()
    img.save(str(folder / "1-phone-and-pc.png"))

    # 2. the phone: code filled in, then the files
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor(T.INK))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    pair = QImage(str(work / f"pair-{lang}.jpg"))
    home = QImage(str(work / f"home-{lang}-dark.jpg"))
    ph = 880
    pw = pair.width() * ph / pair.height()
    x2 = W - 140 - pw
    x1 = x2 - pw - 56
    framed(p, pair, QRectF(place(x1, pw, rtl), (H - ph) / 2, pw, ph), 34, True)
    framed(p, home, QRectF(place(x2, pw, rtl), (H - ph) / 2, pw, ph), 34, True)
    text_block(p, lang, *caps[1], place(100, 640, rtl), 640, True)
    p.end()
    img.save(str(folder / "2-scan-and-connect.png"))

    # 3. light: the PC window with the phone in front
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor(T.IVORY))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    win = QImage(str(work / f"win-{lang}-light.png"))
    k = 780 / win.height()
    ww, wh = win.width() * k, win.height() * k
    wx = W - 230 - ww
    framed(p, win, QRectF(place(wx, ww, rtl), (H - wh) / 2 - 30, ww, wh), 14, False)
    phone = QImage(str(work / f"home-{lang}-light.jpg"))
    ph = 760
    pw = phone.width() * ph / phone.height()
    framed(p, phone, QRectF(place(W - 90 - pw, pw, rtl), H - ph - 70, pw, ph), 32, False)
    text_block(p, lang, *caps[2], place(90, 470, rtl), 470, False)
    p.end()
    img.save(str(folder / "3-dark-or-light.png"))


def main() -> None:
    work, out = Path(sys.argv[1]), Path(sys.argv[2])
    for lang in CAPTIONS:
        compose(work, out, lang)
        print("screenshots for", lang)


if __name__ == "__main__":
    main()
