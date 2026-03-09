import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

DB_NAME = "leetcode_challenge.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            current_streak INTEGER DEFAULT 0,
            max_streak INTEGER DEFAULT 0,
            last_completion_day INTEGER DEFAULT 0,
            leetcode_username TEXT DEFAULT NULL
        )
    ''')

    # Migration: add leetcode_username column if it doesn't exist (for existing DBs)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN leetcode_username TEXT DEFAULT NULL')
    except Exception:
        pass  # Column already exists

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            day INTEGER,
            completed BOOLEAN,
            difficulty TEXT,
            completed_at TIMESTAMP,
            UNIQUE(user_id, day)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS challenge_state (
            id INTEGER PRIMARY KEY,
            current_day INTEGER DEFAULT 1,
            start_date DATE,
            is_active BOOLEAN DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()

def register_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def mark_completion(user_id: int, day: int, completed: bool, difficulty: str = None) -> Dict:
    """Mark completion and return streak info"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Get current user streak info
    cursor.execute('''
        SELECT current_streak, max_streak, last_completion_day
        FROM users WHERE user_id = ?
    ''', (user_id,))
    result = cursor.fetchone()

    old_streak = result[0] if result else 0
    max_streak = result[1] if result else 0
    last_day = result[2] if result else 0

    streak_info = {
        "old_streak": old_streak,
        "new_streak": old_streak,
        "max_streak": max_streak,
        "streak_broken": False,
        "new_record": False
    }

    if completed:
        # Calculate new streak
        if last_day == day - 1:
            # Consecutive day - increase streak
            new_streak = old_streak + 1
        elif last_day == day:
            # Same day - no change
            new_streak = old_streak
        else:
            # Streak broken - start new
            new_streak = 1
            if old_streak > 1:
                streak_info["streak_broken"] = True

        # Check for new record
        if new_streak > max_streak:
            max_streak = new_streak
            streak_info["new_record"] = True

        streak_info["new_streak"] = new_streak
        streak_info["max_streak"] = max_streak

        # Update user streak
        cursor.execute('''
            UPDATE users
            SET current_streak = ?, max_streak = ?, last_completion_day = ?
            WHERE user_id = ?
        ''', (new_streak, max_streak, day, user_id))
    else:
        # Not completed - reset streak if they explicitly skip
        if old_streak > 0:
            streak_info["streak_broken"] = True
            cursor.execute('''
                UPDATE users SET current_streak = 0 WHERE user_id = ?
            ''', (user_id,))
            streak_info["new_streak"] = 0

    # Record completion
    cursor.execute('''
        INSERT OR REPLACE INTO completions (user_id, day, completed, difficulty, completed_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, day, completed, difficulty, datetime.now() if completed else None))

    conn.commit()
    conn.close()

    return streak_info

def get_user_streak(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT current_streak, max_streak FROM users WHERE user_id = ?
    ''', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return {
        "current": result[0] if result else 0,
        "max": result[1] if result else 0
    }

def get_all_streaks() -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, username, first_name, current_streak, max_streak
        FROM users
        WHERE current_streak > 0
        ORDER BY current_streak DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    return [{
        "user_id": r[0],
        "username": r[1],
        "first_name": r[2],
        "current_streak": r[3],
        "max_streak": r[4]
    } for r in results]

def get_day_completions(day: int) -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.username, u.first_name, c.completed
        FROM users u
        LEFT JOIN completions c ON u.user_id = c.user_id AND c.day = ?
    ''', (day,))
    results = cursor.fetchall()
    conn.close()
    return [{"username": r[0], "first_name": r[1], "completed": r[2]} for r in results]

def get_final_report() -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.user_id, u.username, u.first_name, u.max_streak,
               COUNT(CASE WHEN c.completed = 1 THEN 1 END) as completed_days
        FROM users u
        LEFT JOIN completions c ON u.user_id = c.user_id
        GROUP BY u.user_id
        ORDER BY completed_days DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    return [{
        "user_id": r[0],
        "username": r[1],
        "first_name": r[2],
        "max_streak": r[3] or 0,
        "completed_days": r[4] or 0
    } for r in results]

def get_difficulty_stats(user_id: int = None) -> Dict:
    """Get difficulty breakdown - for user or entire group"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if user_id:
        cursor.execute('''
            SELECT difficulty, COUNT(*) as count
            FROM completions
            WHERE user_id = ? AND completed = 1 AND difficulty IS NOT NULL
            GROUP BY difficulty
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT difficulty, COUNT(*) as count
            FROM completions
            WHERE completed = 1 AND difficulty IS NOT NULL
            GROUP BY difficulty
        ''')

    results = cursor.fetchall()
    conn.close()

    stats = {"Easy": 0, "Medium": 0, "Hard": 0}
    for r in results:
        if r[0] in stats:
            stats[r[0]] = r[1]

    return stats

def get_weekly_stats(start_day: int, end_day: int) -> Dict:
    """Get stats for a week range"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Get user completions for the week
    cursor.execute('''
        SELECT u.user_id, u.username, u.first_name,
               COUNT(CASE WHEN c.completed = 1 THEN 1 END) as week_completed,
               u.current_streak
        FROM users u
        LEFT JOIN completions c ON u.user_id = c.user_id
            AND c.day >= ? AND c.day <= ?
        GROUP BY u.user_id
        ORDER BY week_completed DESC
    ''', (start_day, end_day))

    user_stats = cursor.fetchall()

    # Get difficulty breakdown for the week
    cursor.execute('''
        SELECT difficulty, COUNT(*) as count
        FROM completions
        WHERE day >= ? AND day <= ? AND completed = 1
        GROUP BY difficulty
    ''', (start_day, end_day))

    diff_stats = cursor.fetchall()

    # Get total completions
    cursor.execute('''
        SELECT COUNT(*) FROM completions
        WHERE day >= ? AND day <= ? AND completed = 1
    ''', (start_day, end_day))

    total = cursor.fetchone()[0]

    conn.close()

    return {
        "users": [{
            "user_id": r[0],
            "username": r[1],
            "first_name": r[2],
            "week_completed": r[3] or 0,
            "current_streak": r[4] or 0
        } for r in user_stats],
        "difficulty": {r[0]: r[1] for r in diff_stats},
        "total_completions": total or 0
    }

def get_current_day() -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT current_day FROM challenge_state WHERE id = 1')
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 1

def set_current_day(day: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO challenge_state (id, current_day, is_active)
        VALUES (1, ?, 1)
    ''', (day,))
    conn.commit()
    conn.close()

def get_non_responders(day: int) -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.user_id, u.username, u.first_name, u.current_streak
        FROM users u
        LEFT JOIN completions c ON u.user_id = c.user_id AND c.day = ?
        WHERE c.id IS NULL
    ''', (day,))
    results = cursor.fetchall()
    conn.close()
    return [{
        "user_id": r[0],
        "username": r[1],
        "first_name": r[2],
        "current_streak": r[3] or 0
    } for r in results]

def get_topic_stats() -> Dict:
    """Get completion stats by topic"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT day FROM completions WHERE completed = 1
    ''')
    results = cursor.fetchall()
    conn.close()

    from problems import PROBLEMS

    topic_counts = {}
    for r in results:
        day = r[0]
        if day <= len(PROBLEMS):
            problem = PROBLEMS[day - 1]
            for topic in problem.get("topics", []):
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    return topic_counts


# ============== LEETCODE USERNAME FUNCTIONS ==============

def set_leetcode_username(user_id: int, leetcode_username: str):
    """Store a user's LeetCode username."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET leetcode_username = ? WHERE user_id = ?
    ''', (leetcode_username, user_id))
    conn.commit()
    conn.close()

def get_leetcode_username(user_id: int) -> Optional[str]:
    """Get a user's linked LeetCode username."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT leetcode_username FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result and result[0] else None

def get_all_users_with_leetcode() -> List[Dict]:
    """Return all users who have linked a LeetCode username."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, username, first_name, leetcode_username
        FROM users
        WHERE leetcode_username IS NOT NULL AND leetcode_username != ''
    ''')
    results = cursor.fetchall()
    conn.close()
    return [{
        "user_id": r[0],
        "username": r[1],
        "first_name": r[2],
        "leetcode_username": r[3]
    } for r in results]

def is_already_completed(user_id: int, day: int) -> bool:
    """Check if a user has already been marked completed for a day."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT completed FROM completions
        WHERE user_id = ? AND day = ? AND completed = 1
    ''', (user_id, day))
    result = cursor.fetchone()
    conn.close()
    return result is not None
