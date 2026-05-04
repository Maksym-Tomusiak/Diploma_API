from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from models.user_action_log import UserActionLog
from db import SessionLocal

logger = logging.getLogger(__name__)

def cleanup_old_logs(days: int = 14):
    """
    Delete UserActionLog entries older than the specified number of days.
    """
    logger.info(f"Starting cleanup of logs older than {days} days...")
    
    db: Session = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Count logs before deletion
        count_before = db.query(UserActionLog).count()
        
        # Perform deletion
        deleted = db.query(UserActionLog).filter(
            UserActionLog.created_at < cutoff_date
        ).delete(synchronize_session=False)
        
        db.commit()
        
        count_after = db.query(UserActionLog).count()
        
        logger.info(
            f"Cleanup complete. Deleted {deleted} log entries. "
            f"Remaining: {count_after} (was {count_before})"
        )
        return deleted
    except Exception as e:
        db.rollback()
        logger.error(f"Error during log cleanup: {e}")
        return 0
    finally:
        db.close()
