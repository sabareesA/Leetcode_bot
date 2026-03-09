import asyncio
from datetime import datetime
from telegram import Update, Bot, Poll
from telegram.ext import (
    Application,
    CommandHandler,
    PollAnswerHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import BOT_TOKEN, GROUP_CHAT_ID, DAILY_QUESTION_TIME, REMINDER_TIME, TIMEZONE
from problems import PROBLEMS, DIFFICULTY_EMOJI, TOPIC_EMOJI
from database import (
    init_db, register_user, mark_completion,
    get_final_report, get_current_day, set_current_day,
    get_non_responders, get_day_completions, get_user_streak,
    get_all_streaks, get_difficulty_stats, get_weekly_stats,
    get_topic_stats,
    set_leetcode_username, get_leetcode_username,
    get_all_users_with_leetcode, is_already_completed
)
from leetcode_api import check_problem_solved, verify_leetcode_user

# Store poll_id -> day mapping
poll_data = {}

# ============== HELPER FUNCTIONS ==============

def get_streak_emoji(streak: int) -> str:
    """Get fire emojis based on streak length"""
    if streak >= 20:
        return "🔥" * 5 + " 👑"
    elif streak >= 14:
        return "🔥" * 4
    elif streak >= 7:
        return "🔥" * 3
    elif streak >= 3:
        return "🔥" * 2
    elif streak >= 1:
        return "🔥"
    return ""

def format_topics(topics: list) -> str:
    """Format topics with emojis"""
    formatted = []
    for topic in topics[:4]:  # Limit to 4 topics
        emoji = TOPIC_EMOJI.get(topic, "📌")
        formatted.append(f"{emoji} {topic}")
    return " | ".join(formatted)

# ============== USER COMMANDS ==============

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        # Skip if it's a bot
        if member.is_bot:
            continue

        # Register the user
        register_user(member.id, member.username, member.first_name)

        welcome_text = f"""
👋 *Welcome {member.first_name}!*

You've joined the *30-Day LeetCode Challenge!* 🚀

📝 Here's how to get started:
1. Type /start to register
2. Use /today to see today's problem
3. Solve it & vote ✅ in the poll
4. Check /leaderboard for rankings

Type /help to see all commands.

Good luck! 💪
        """

        await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)

    welcome_text = f"""
👋 *Welcome {user.first_name}!*

🚀 You're now registered for the *30-Day LeetCode Challenge!*

━━━━━━━━━━━━━━━━━━━━━━

📅 *Daily Schedule:*
• 9:00 AM - New problem posted
• 8:00 PM - Reminder notification
• Sunday 9 PM - Weekly summary

━━━━━━━━━━━━━━━━━━━━━━

📋 *Available Commands:*

*📝 Daily Challenge:*
/today - Get today's problem

*🔗 LeetCode Sync:*
/setleetcode - Link your LeetCode account (auto-tracking!)
/checknow - Manually trigger an instant check

*📊 Your Stats:*
/progress - Full stats dashboard
/streak - Your current streak
/difficulty - Difficulty breakdown

*🏆 Leaderboards:*
/leaderboard - Group rankings
/streaks - Streak leaderboard
/topics - Topic-wise stats

*📄 Other:*
/report - Full 30-day report
/help - Show all commands

━━━━━━━━━━━━━━━━━━━━━━

🔥 *How It Works:*
1️⃣ Daily problem posted at 9 AM
2️⃣ Link your LeetCode account with /setleetcode
3️⃣ Solve the problem — bot auto-detects it every hour! 🤖
4️⃣ Or vote ✅ in the poll manually if you prefer
5️⃣ Build your streak & climb the leaderboard!

💪 *Let's start coding!*
Use /today to see the current problem.
    """

    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *LeetCode Challenge Bot - Help*

📋 *User Commands:*

/start - Register for the challenge
/today - Get today's problem with topics
/setleetcode - Link your LeetCode username for auto-tracking
/checknow - Instantly check if you've solved today's problem
/progress - Your personal stats dashboard
/streak - View your current & best streak
/streaks - Active streaks leaderboard
/leaderboard - Group rankings by completion
/difficulty - Easy/Medium/Hard breakdown
/topics - Topic-wise completion stats
/report - Full 30-day challenge report
/help - Show this help message

⏰ *Daily Schedule:*
• 9:00 AM - New problem posted & pinned
• 8:00 PM - Reminder for non-responders
• Sunday 9 PM - Weekly summary

🔥 *Streak System:*
• Complete daily to build your streak
• Miss a day = streak resets
• Milestones: 3, 7, 14, 21, 30 days

📊 *How to Participate:*
1. Use /start to register
2. Link your LeetCode account with /setleetcode
3. Solve the daily problem — bot auto-detects every hour! 🤖
4. Or vote in the poll manually as backup
5. Check /leaderboard to see rankings

💡 *Tips:*
• Pin the daily problem message
• Set a personal reminder
• Help others in the group!

Good luck! 💪
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def get_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_day = get_current_day()
    if current_day > 30:
        await update.message.reply_text("🎉 The 30-day challenge is complete!")
        return

    problem = PROBLEMS[current_day - 1]
    diff_emoji = DIFFICULTY_EMOJI.get(problem['difficulty'], "⚪")
    topics_formatted = format_topics(problem['topics'])

    await update.message.reply_text(
        f"📝 *Day {current_day}/30*\n\n"
        f"*{problem['title']}*\n"
        f"{diff_emoji} Difficulty: {problem['difficulty']}\n\n"
        f"🏷️ *Topics:*\n{topics_formatted}\n\n"
        f"🔗 [Solve on LeetCode]({problem['url']})",
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def get_streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    streak = get_user_streak(user.id)
    streak_emoji = get_streak_emoji(streak['current'])

    await update.message.reply_text(
        f"🔥 *{user.first_name}'s Streak*\n\n"
        f"Current Streak: *{streak['current']} days* {streak_emoji}\n"
        f"Best Streak: *{streak['max']} days* 🏆\n\n"
        f"{'Keep it going! 💪' if streak['current'] > 0 else 'Start your streak today! 🚀'}",
        parse_mode='Markdown'
    )

async def get_streaks_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    streaks = get_all_streaks()

    if not streaks:
        await update.message.reply_text("No active streaks yet! Be the first! 🔥")
        return

    text = "🔥 *Active Streaks Leaderboard* 🔥\n\n"

    for i, user in enumerate(streaks[:10]):
        name = user['first_name'] or user['username'] or "Anonymous"
        streak_emoji = get_streak_emoji(user['current_streak'])

        if i == 0:
            medal = "👑"
        elif i == 1:
            medal = "🥈"
        elif i == 2:
            medal = "🥉"
        else:
            medal = f"{i+1}."

        text += f"{medal} {name}: *{user['current_streak']} days* {streak_emoji}\n"
        text += f"    └ Best: {user['max_streak']} days\n"

    await update.message.reply_text(text, parse_mode='Markdown')

async def get_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    report = get_final_report()
    streak = get_user_streak(user.id)
    diff_stats = get_difficulty_stats(user.id)

    user_data = next((r for r in report if r.get('user_id') == user.id), None)
    current_day = get_current_day()

    if user_data:
        completed = user_data['completed_days']
        percentage = (completed / min(current_day, 30)) * 100
        streak_emoji = get_streak_emoji(streak['current'])

        await update.message.reply_text(
            f"📊 *{user.first_name}'s Progress*\n\n"
            f"✅ Completed: *{completed}/{min(current_day, 30)}* days\n"
            f"📈 Completion Rate: *{percentage:.1f}%*\n\n"
            f"🔥 Current Streak: *{streak['current']} days* {streak_emoji}\n"
            f"🏆 Best Streak: *{streak['max']} days*\n\n"
            f"📊 *Difficulty Breakdown:*\n"
            f"🟢 Easy: {diff_stats['Easy']}\n"
            f"🟡 Medium: {diff_stats['Medium']}\n"
            f"🔴 Hard: {diff_stats['Hard']}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("No progress data found. Use /start to register!")

async def get_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = get_final_report()
    current_day = get_current_day()

    text = "🏆 *Leaderboard* 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, user in enumerate(report[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = user['first_name'] or user['username'] or "Anonymous"
        percentage = (user['completed_days'] / min(current_day, 30)) * 100
        streak_emoji = get_streak_emoji(user.get('max_streak', 0))

        text += f"{medal} *{name}*\n"
        text += f"    └ {user['completed_days']}/{min(current_day, 30)} days ({percentage:.0f}%) {streak_emoji}\n"

    await update.message.reply_text(text, parse_mode='Markdown')

async def get_difficulty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Group stats
    group_stats = get_difficulty_stats()
    total = sum(group_stats.values())

    # User stats
    user = update.effective_user
    user_stats = get_difficulty_stats(user.id)
    user_total = sum(user_stats.values())

    text = "📊 *Difficulty Statistics*\n\n"

    text += "*👥 Group Total:*\n"
    if total > 0:
        text += f"🟢 Easy: {group_stats['Easy']} ({group_stats['Easy']/total*100:.0f}%)\n"
        text += f"🟡 Medium: {group_stats['Medium']} ({group_stats['Medium']/total*100:.0f}%)\n"
        text += f"🔴 Hard: {group_stats['Hard']} ({group_stats['Hard']/total*100:.0f}%)\n"
    else:
        text += "No completions yet!\n"

    text += f"\n*👤 Your Stats:*\n"
    if user_total > 0:
        text += f"🟢 Easy: {user_stats['Easy']}\n"
        text += f"🟡 Medium: {user_stats['Medium']}\n"
        text += f"🔴 Hard: {user_stats['Hard']}\n"
    else:
        text += "Complete some problems to see stats!\n"

    await update.message.reply_text(text, parse_mode='Markdown')

async def get_topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic_stats = get_topic_stats()

    if not topic_stats:
        await update.message.reply_text("No topic data yet! Complete some problems first.")
        return

    # Sort by count
    sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)

    text = "🏷️ *Topic-wise Completions*\n\n"

    for topic, count in sorted_topics[:12]:
        emoji = TOPIC_EMOJI.get(topic, "📌")
        bar = "█" * min(count, 10)  # Visual bar
        text += f"{emoji} *{topic}*\n    └ {bar} {count}\n"

    await update.message.reply_text(text, parse_mode='Markdown')

# ============== AUTOMATIC FEATURES ==============

async def send_daily_question(context: ContextTypes.DEFAULT_TYPE):
    current_day = get_current_day()

    if current_day > 30:
        await send_final_report(context)
        return

    problem = PROBLEMS[current_day - 1]
    diff_emoji = DIFFICULTY_EMOJI.get(problem['difficulty'], "⚪")
    topics_formatted = format_topics(problem['topics'])

    # Send the question message
    message = await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=f"""
🔥 *Day {current_day}/30 - LeetCode Challenge* 🔥

📝 *Problem:* {problem['title']}
{diff_emoji} *Difficulty:* {problem['difficulty']}

🏷️ *Topics:*
{topics_formatted}

🔗 [Solve on LeetCode]({problem['url']})

Good luck everyone! 💪
Vote in the poll below once you're done!
        """,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

    # Pin the message
    await context.bot.pin_chat_message(
        chat_id=GROUP_CHAT_ID,
        message_id=message.message_id
    )

    # Create a poll
    poll_message = await context.bot.send_poll(
        chat_id=GROUP_CHAT_ID,
        question=f"Day {current_day}: Did you complete '{problem['title']}'?",
        options=["✅ Yes, completed!", "🔄 Working on it", "❌ Skipped today"],
        is_anonymous=False
    )

    # Store poll data for tracking
    poll_data[poll_message.poll.id] = {
        "day": current_day,
        "difficulty": problem['difficulty']
    }

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    user_id = answer.user.id
    poll_id = answer.poll_id

    if poll_id in poll_data:
        poll_info = poll_data[poll_id]
        day = poll_info["day"]
        difficulty = poll_info["difficulty"]
        selected_option = answer.option_ids[0] if answer.option_ids else -1

        # Register user if not exists
        register_user(user_id, answer.user.username, answer.user.first_name)

        # Mark completion (option 0 = completed)
        completed = selected_option == 0
        streak_info = mark_completion(user_id, day, completed, difficulty if completed else None)

        # Send streak update if significant
        if completed and streak_info["new_streak"] > 0:
            name = answer.user.first_name or answer.user.username
            streak_emoji = get_streak_emoji(streak_info["new_streak"])

            if streak_info["new_record"] and streak_info["new_streak"] > 1:
                # New personal record!
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🎉 *NEW RECORD!* 🎉\n\n"
                         f"@{answer.user.username or name} just hit a *{streak_info['new_streak']}-day streak!* {streak_emoji}\n"
                         f"That's their new personal best! 🏆",
                    parse_mode='Markdown'
                )
            elif streak_info["new_streak"] in [3, 7, 14, 21, 30]:
                # Milestone reached!
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🎯 *STREAK MILESTONE!* 🎯\n\n"
                         f"@{answer.user.username or name} is on a *{streak_info['new_streak']}-day streak!* {streak_emoji}\n"
                         f"Keep it up! 💪",
                    parse_mode='Markdown'
                )

        # Notify if streak broken
        if streak_info.get("streak_broken") and streak_info["old_streak"] >= 3:
            name = answer.user.first_name or answer.user.username
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"💔 @{answer.user.username or name}'s {streak_info['old_streak']}-day streak ended.\n"
                     f"Start a new one tomorrow! 💪",
                parse_mode='Markdown'
            )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    current_day = get_current_day()
    non_responders = get_non_responders(current_day)

    if non_responders:
        text = "⏰ *Evening Reminder!* ⏰\n\n"

        for user in non_responders:
            name = f"@{user['username']}" if user['username'] else user['first_name']
            if user['current_streak'] > 0:
                text += f"• {name} - Don't lose your *{user['current_streak']}-day streak!* 🔥\n"
            else:
                text += f"• {name}\n"

        text += "\nComplete today's problem and vote in the poll! 💪"

        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode='Markdown'
        )

async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Send weekly summary every Sunday"""
    current_day = get_current_day()

    # Calculate week range
    week_end = current_day - 1
    week_start = max(1, week_end - 6)
    week_num = (week_end // 7) + 1

    if week_end < 1:
        return

    stats = get_weekly_stats(week_start, week_end)

    text = f"📊 *Week {week_num} Summary* 📊\n"
    text += f"_(Days {week_start} - {week_end})_\n\n"

    # Top performers
    text += "🏆 *Top Performers:*\n"
    for i, user in enumerate(stats['users'][:5]):
        if user['week_completed'] == 0:
            continue
        name = user['first_name'] or user['username'] or "Anonymous"
        medals = ["🥇", "🥈", "🥉"]
        medal = medals[i] if i < 3 else f"{i+1}."
        streak_emoji = get_streak_emoji(user['current_streak'])
        text += f"{medal} {name}: {user['week_completed']}/7 days {streak_emoji}\n"

    # Difficulty breakdown
    text += "\n📈 *Difficulty Breakdown:*\n"
    diff = stats.get('difficulty', {})
    text += f"🟢 Easy: {diff.get('Easy', 0)}\n"
    text += f"🟡 Medium: {diff.get('Medium', 0)}\n"
    text += f"🔴 Hard: {diff.get('Hard', 0)}\n"

    # Total completions
    text += f"\n✅ *Total Completions:* {stats['total_completions']}\n"

    # Active streaks
    all_streaks = get_all_streaks()
    if all_streaks:
        top_streak = all_streaks[0]
        text += f"\n🔥 *Longest Active Streak:*\n"
        text += f"{top_streak['first_name']}: {top_streak['current_streak']} days! 🔥\n"

    text += "\n_Keep pushing! New week, new goals!_ 💪"

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=text,
        parse_mode='Markdown'
    )

async def increment_day(context: ContextTypes.DEFAULT_TYPE):
    current_day = get_current_day()
    set_current_day(current_day + 1)

async def send_final_report(context: ContextTypes.DEFAULT_TYPE):
    report = get_final_report()
    diff_stats = get_difficulty_stats()

    text = "🎉 *30-Day LeetCode Challenge Complete!* 🎉\n\n"
    text += "📊 *Final Results:*\n\n"

    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(report[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = user['first_name'] or user['username'] or "Anonymous"
        percentage = (user['completed_days'] / 30) * 100
        streak_emoji = get_streak_emoji(user.get('max_streak', 0))

        text += f"{medal} *{name}*\n"
        text += f"    └ {user['completed_days']}/30 ({percentage:.0f}%)\n"
        text += f"    └ Best Streak: {user.get('max_streak', 0)} days {streak_emoji}\n"

    text += "\n📈 *Group Difficulty Stats:*\n"
    text += f"🟢 Easy: {diff_stats['Easy']}\n"
    text += f"🟡 Medium: {diff_stats['Medium']}\n"
    text += f"🔴 Hard: {diff_stats['Hard']}\n"

    text += "\n🙌 *Great job everyone! Keep coding!* 🚀"

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=text,
        parse_mode='Markdown'
    )

async def set_leetcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link a LeetCode username to the user's Telegram account."""
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)

    if not context.args:
        current = get_leetcode_username(user.id)
        if current:
            await update.message.reply_text(
                f"🔗 Your linked LeetCode username: *{current}*\n\n"
                f"To change it, use:\n`/setleetcode <your_username>`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Please provide your LeetCode username.\n\n"
                "Usage: `/setleetcode <your_username>`\n\n"
                "Example: `/setleetcode john_doe`",
                parse_mode='Markdown'
            )
        return

    lc_username = context.args[0].strip()

    # Verify the username exists on LeetCode
    await update.message.reply_text(f"🔄 Verifying LeetCode username *{lc_username}*...", parse_mode='Markdown')

    is_valid = await verify_leetcode_user(lc_username)
    if not is_valid:
        await update.message.reply_text(
            f"❌ Username *{lc_username}* not found on LeetCode.\n\n"
            f"Please check your username and try again.\n"
            f"Your LeetCode username is in your profile URL:\n"
            f"`https://leetcode.com/u/your-username/`",
            parse_mode='Markdown'
        )
        return

    set_leetcode_username(user.id, lc_username)
    await update.message.reply_text(
        f"✅ Linked LeetCode account: *{lc_username}*\n\n"
        f"The bot will now automatically check your submissions every hour and mark problems as done when you solve them! 🚀\n\n"
        f"No more voting in the poll — just solve and we'll detect it! 🎯",
        parse_mode='Markdown'
    )


async def check_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Immediately check if the user has solved today's problem on LeetCode."""
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)

    lc_username = get_leetcode_username(user.id)
    if not lc_username:
        await update.message.reply_text(
            "❌ You haven't linked your LeetCode account yet.\n\n"
            "Use `/setleetcode <your_username>` first!",
            parse_mode='Markdown'
        )
        return

    current_day = get_current_day()
    if current_day > 30:
        await update.message.reply_text("🎉 The 30-day challenge is already complete!")
        return

    # Already done?
    if is_already_completed(user.id, current_day):
        await update.message.reply_text(
            "✅ You've already been marked as done for today! Keep it up! 🔥",
            parse_mode='Markdown'
        )
        return

    problem = PROBLEMS[current_day - 1]

    msg = await update.message.reply_text(
        f"🔄 Checking your LeetCode submissions for *{problem['title']}*...",
        parse_mode='Markdown'
    )

    try:
        solved = await check_problem_solved(lc_username, problem["url"])
    except Exception:
        await msg.edit_text("⚠️ Failed to reach LeetCode API. Please try again in a moment.")
        return

    if solved:
        streak_info = mark_completion(user.id, current_day, True, problem["difficulty"])
        streak_emoji = get_streak_emoji(streak_info["new_streak"])

        await msg.edit_text(
            f"✅ *Confirmed!* You solved *{problem['title']}* today!\n"
            f"Streak: *{streak_info['new_streak']} days* {streak_emoji}",
            parse_mode='Markdown'
        )

        # Announce in group if command was in private, or just send group message
        name = user.first_name or user.username
        mention = f"@{user.username}" if user.username else name
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"✅ {mention} just checked in — solved *{problem['title']}*! 🎯\n"
                 f"Streak: *{streak_info['new_streak']} days* {streak_emoji}",
            parse_mode='Markdown'
        )

        # Milestones
        if streak_info["new_record"] and streak_info["new_streak"] > 1:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"🎉 *NEW RECORD!* {mention} hit a *{streak_info['new_streak']}-day streak!* {streak_emoji} 🏆",
                parse_mode='Markdown'
            )
        elif streak_info["new_streak"] in [3, 7, 14, 21, 30]:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"🎯 *STREAK MILESTONE!* {mention} is on a *{streak_info['new_streak']}-day streak!* {streak_emoji}",
                parse_mode='Markdown'
            )
    else:
        await msg.edit_text(
            f"❌ No submission found for *{problem['title']}* today on LeetCode account `{lc_username}`.\n\n"
            f"Make sure you:\n"
            f"• Submitted on LeetCode (not just ran locally)\n"
            f"• Got an *Accepted* verdict\n"
            f"• Are logged in as `{lc_username}`\n\n"
            f"Try again after submitting! 💪",
            parse_mode='Markdown'
        )


async def auto_check_leetcode_submissions(context: ContextTypes.DEFAULT_TYPE):
    """
    Scheduled job: Check every user's LeetCode submissions for today's problem.
    Runs every hour. Automatically marks completion if the problem is solved.
    """
    current_day = get_current_day()
    if current_day > 30:
        return

    problem = PROBLEMS[current_day - 1]
    users = get_all_users_with_leetcode()

    for user in users:
        user_id = user["user_id"]

        # Skip if already marked as completed
        if is_already_completed(user_id, current_day):
            continue

        try:
            solved = await check_problem_solved(user["leetcode_username"], problem["url"])
        except Exception:
            continue

        if solved:
            streak_info = mark_completion(user_id, current_day, True, problem["difficulty"])
            name = user["first_name"] or user["username"] or user["leetcode_username"]
            streak_emoji = get_streak_emoji(streak_info["new_streak"])

            # Announce in group
            mention = f"@{user['username']}" if user['username'] else name
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"🤖 *Auto-detected!* {mention} just solved *{problem['title']}* on LeetCode! ✅\n"
                     f"Streak: *{streak_info['new_streak']} days* {streak_emoji}",
                parse_mode='Markdown'
            )

            # Streak milestones
            if streak_info["new_record"] and streak_info["new_streak"] > 1:
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🎉 *NEW RECORD!* 🎉\n\n"
                         f"{mention} hit a *{streak_info['new_streak']}-day streak!* {streak_emoji}\n"
                         f"Personal best! 🏆",
                    parse_mode='Markdown'
                )
            elif streak_info["new_streak"] in [3, 7, 14, 21, 30]:
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🎯 *STREAK MILESTONE!* 🎯\n\n"
                         f"{mention} is on a *{streak_info['new_streak']}-day streak!* {streak_emoji}",
                    parse_mode='Markdown'
                )

        # Small delay between API calls to be polite
        await asyncio.sleep(1)


# ============== ADMIN COMMANDS ==============

async def admin_start_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_current_day(1)
    await update.message.reply_text("✅ Challenge started! Day 1 begins.")
    await send_daily_question(context)

async def admin_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_final_report(context)

async def admin_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_weekly_summary(context)

# ============== MAIN ==============

async def post_init(application: Application):
    """Start scheduler after bot is initialized"""
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))

    # Parse times
    question_hour, question_minute = map(int, DAILY_QUESTION_TIME.split(':'))
    reminder_hour, reminder_minute = map(int, REMINDER_TIME.split(':'))

    # Daily question at 9 AM
    scheduler.add_job(
        send_daily_question,
        CronTrigger(hour=question_hour, minute=question_minute),
        args=[application],
        id='daily_question',
        replace_existing=True
    )

    # Reminder at 8 PM
    scheduler.add_job(
        send_reminder,
        CronTrigger(hour=reminder_hour, minute=reminder_minute),
        args=[application],
        id='daily_reminder',
        replace_existing=True
    )

    # Increment day at midnight
    scheduler.add_job(
        increment_day,
        CronTrigger(hour=0, minute=0),
        args=[application],
        id='increment_day',
        replace_existing=True
    )

    # Weekly summary on Sunday at 9 PM
    scheduler.add_job(
        send_weekly_summary,
        CronTrigger(day_of_week='sun', hour=21, minute=0),
        args=[application],
        id='weekly_summary',
        replace_existing=True
    )

    # Auto-check LeetCode submissions every hour
    scheduler.add_job(
        auto_check_leetcode_submissions,
        CronTrigger(minute=30),  # Runs at HH:30 every hour
        args=[application],
        id='leetcode_auto_check',
        replace_existing=True
    )

    scheduler.start()

    print("🤖 LeetCode Challenge Bot is running...")
    print(f"📅 Daily questions at {DAILY_QUESTION_TIME}")
    print(f"⏰ Reminders at {REMINDER_TIME}")
    print(f"📊 Weekly summary: Sunday 9 PM")
    print(f"🔍 LeetCode auto-check: every hour at :30")
    print(f"🌍 Timezone: {TIMEZONE}")


def main():
    # Initialize database
    init_db()

    # Create application with post_init callback
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # User command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", get_today))
    application.add_handler(CommandHandler("setleetcode", set_leetcode_command))
    application.add_handler(CommandHandler("checknow", check_now_command))
    application.add_handler(CommandHandler("progress", get_progress))
    application.add_handler(CommandHandler("streak", get_streak_command))
    application.add_handler(CommandHandler("streaks", get_streaks_leaderboard))
    application.add_handler(CommandHandler("leaderboard", get_leaderboard))
    application.add_handler(CommandHandler("difficulty", get_difficulty_command))
    application.add_handler(CommandHandler("topics", get_topics_command))
    application.add_handler(CommandHandler("report", admin_report))

    # Admin commands
    application.add_handler(CommandHandler("startchallenge", admin_start_challenge))
    application.add_handler(CommandHandler("weeklysummary", admin_weekly))

    # Poll handler
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    # Welcome new members
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        welcome_new_member
    ))

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
