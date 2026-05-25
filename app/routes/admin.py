import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename

bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg', 'webp'}
MAX_SIZE_MB = 2


def _allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.get('/')
def index():
    logo_path = os.path.join(current_app.root_path, 'static', 'uploads', 'logo.png')
    has_logo = os.path.exists(logo_path)
    return render_template('admin/index.html', has_logo=has_logo)


@bp.post('/logo/upload')
def upload_logo():
    file = request.files.get('logo')

    if not file or file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin.index'))

    if not _allowed(file.filename):
        flash('Formato não permitido. Use PNG, JPG, SVG ou WEBP.', 'error')
        return redirect(url_for('admin.index'))

    # Verifica tamanho lendo até MAX_SIZE_MB + 1 byte
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_SIZE_MB * 1024 * 1024:
        flash(f'Arquivo muito grande. Máximo {MAX_SIZE_MB} MB.', 'error')
        return redirect(url_for('admin.index'))

    uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    # Sempre salva como logo.png (substitui a anterior)
    dest = os.path.join(uploads_dir, 'logo.png')
    file.save(dest)

    flash('Logo atualizada com sucesso!', 'success')
    return redirect(url_for('admin.index'))


@bp.post('/logo/remove')
def remove_logo():
    logo_path = os.path.join(current_app.root_path, 'static', 'uploads', 'logo.png')
    if os.path.exists(logo_path):
        os.remove(logo_path)
        flash('Logo removida. O portal voltará ao título padrão.', 'success')
    else:
        flash('Nenhuma logo encontrada.', 'error')
    return redirect(url_for('admin.index'))
