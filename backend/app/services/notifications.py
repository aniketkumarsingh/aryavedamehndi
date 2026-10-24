import uuid

from sqlalchemy.orm import Session

from app.models.notification import Notification


def notify(db: Session, user_id: uuid.UUID, category: str, title: str, body: str | None = None, link_url: str | None = None) -> None:
    """Creates an in-app notification. Doesn't commit - callers are
    already inside a request that commits its own transaction; this just
    adds the row so it goes out with that same commit."""
    db.add(Notification(user_id=user_id, category=category, title=title, body=body, link_url=link_url))


def notify_admins(db: Session, title: str, body: str | None = None, link_url: str | None = None) -> None:
    from app.models.user import User

    for admin in db.query(User).filter(User.role == "admin", User.is_active.is_(True)).all():
        notify(db, admin.id, "system", title, body, link_url)
