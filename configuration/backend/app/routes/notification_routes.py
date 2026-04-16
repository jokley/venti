import io
import qrcode
from flask import Blueprint, send_file, redirect
from app.config import Config

notification_bp = Blueprint('notification', __name__)

# Die Routen im Backend
@notification_bp.route('/qr/ntfy')
def qr_ntfy_abo():
    # Der Deep Link für das Abo
    return _generate_qr(f"{Config.NTFY_BASE_URL}/{Config.NTFY_TOPIC}")

@notification_bp.route('/qr/ios')
def qr_ios_store():
    # Der Link zum App Store
    return _generate_qr(Config.URL_IOS_STORE)

@notification_bp.route('/qr/android')
def qr_android_store():
    # Der Link zum Play Store
    return _generate_qr(Config.URL_ANDROID_STORE)

# Interne Hilfsfunktion (um Code-Duplikate zu vermeiden)
def _generate_qr(data):
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

@notification_bp.route('/qr/ntfy/open')
def open_ntfy_link():
    # Der Klick-Link: Nutzt Deep-Linking von ntfy.sh
    return redirect(f"{Config.NTFY_BASE_URL}/{Config.NTFY_TOPIC}")
