import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.models import AuditEvent


def record_audit_event(
    db: Session,
    *,
    actor_id: Optional[str],
    action: str,
    object_type: str,
    object_id: Optional[str],
    details: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        details_json=json.dumps(details or {}, sort_keys=True, default=str),
    )
    db.add(event)
    return event

