import bcrypt
from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db, login_manager


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_users"

    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(80),  unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active    = db.Column(db.Boolean, default=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login   = db.Column(db.DateTime, nullable=True)

    # Perfil
    full_name    = db.Column(db.String(120), nullable=True)
    phone        = db.Column(db.String(30),  nullable=True)
    email        = db.Column(db.String(120), nullable=True)
    avatar_path  = db.Column(db.String(256), nullable=True)

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt()
        ).decode()

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())

    def get_id(self):
        return str(self.id)

    @property
    def display_name(self) -> str:
        return self.full_name or self.username

    @property
    def avatar_url(self) -> str | None:
        if self.avatar_path:
            return f"/admin/media/{self.avatar_path}"
        return None


@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))
