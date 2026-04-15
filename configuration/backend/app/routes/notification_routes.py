import io
import qrcode
from flask import Blueprint, send_file, redirect
from app.config import Config

notification_bp = Blueprint('notification', __name__)

@notification_bp.route('/qr/ntfy')
def generate_ntfy_qr():
    # Erzeugt das Bild für das Panel
    ntfy_url = f"{Config.NTFY_BASE_URL}/{Config.NTFY_TOPIC}"
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(ntfy_url)
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
