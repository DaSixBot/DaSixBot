import os
import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, Select
import asyncio
import json
import random
import aiohttp
import io
import re
import time
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

# Pillow for welcome images
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("[WARNING] Pillow not installed. Welcome images disabled. Run: pip install Pillow")

# Load environment variables
load_dotenv()

# -------------------
# ANTI-SPAM SYSTEM
# -------------------
class AntiSpamSystem:
    def __init__(self, messages_per_interval=5, interval_seconds=5, timeout_seconds=300):
        self.messages_per_interval = messages_per_interval
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.user_messages = defaultdict(list)
        self.muted_users = {}

    def is_user_muted(self, user_id):
        if user_id in self.muted_users:
            if datetime.now(timezone.utc) < self.muted_users[user_id]:
                return True
            else:
                del self.muted_users[user_id]
        return False

    def add_message(self, user_id):
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(seconds=self.interval_seconds)
        self.user_messages[user_id] = [
            msg_time for msg_time in self.user_messages[user_id]
            if msg_time > cutoff_time
        ]
        self.user_messages[user_id].append(now)
        if len(self.user_messages[user_id]) > self.messages_per_interval:
            return True
        return False

    def mute_user(self, user_id):
        unmute_time = datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds)
        self.muted_users[user_id] = unmute_time

    def get_mute_remaining(self, user_id):
        if user_id in self.muted_users:
            remaining = (self.muted_users[user_id] - datetime.now(timezone.utc)).total_seconds()
            return max(0, remaining)
        return 0


# -------------------------
# CHANNEL SILENT MODE SYSTEM
# -------------------------
SILENT_CHANNELS = {}

async def setup_silent_channel(channel_id, guild):
    try:
        channel = guild.get_channel(channel_id)
        if not channel:
            print(f"[SilentMode] Channel {channel_id} not found")
            return
        overwrites = channel.overwrites.get(guild.default_role, discord.PermissionOverwrite())
        overwrites.view_channel = True
        overwrites.send_messages = True
        overwrites.read_message_history = True
        await channel.set_permissions(guild.default_role, overwrite=overwrites)
        print(f"[SilentMode] Channel {channel.name} is now silent by default")
    except Exception as e:
        print(f"[SilentMode] Error setting up silent channel: {e}")


# -------------------------
# Bot Initialization & Configs
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# Track bot start time for !uptime
BOT_START_TIME = time.time()

anti_spam = AntiSpamSystem(
    messages_per_interval=5,
    interval_seconds=5,
    timeout_seconds=300
)

PAYMENTS_FILE        = "payments.json"
CONFIG_FILE          = "server_config.json"
REMINDERS_FILE       = "reminders.json"
TEMPMUTE_FILE        = "tempmutes.json"
CUSTOM_COMMANDS_FILE = "custom_commands.json"
AFK_FILE             = "afk.json"
WARNINGS_FILE        = "warnings.json"
SCHEDULES_FILE       = "scheduled_announcements.json"

# Roles allowed to run giveaway commands
GIVEAWAY_ALLOWED_ROLES = ["Moderator", "Developer", "Support", "Owner"]

# Ticket auto-close: hours of OPENER inactivity before ticket closes
TICKET_IDLE_HOURS = 24

# Track opener activity per ticket channel  {channel_id: {"opener_id": int, "last_opener_message": datetime}}
TICKET_ACTIVITY: dict = {}

# Escalating warn punishments  {warn_count: ("action", duration_seconds_or_None, "label")}
WARN_THRESHOLDS = {
    3:  ("mute", 3600,   "1-hour mute"),
    5:  ("mute", 86400,  "24-hour mute"),
    7:  ("kick", None,   "kick"),
    10: ("ban",  None,   "permanent ban"),
}


# -------------------------
# Config helpers
# -------------------------
def load_server_config(guild_id):
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            all_configs = json.load(f)
            return all_configs.get(str(guild_id), {})
    return {}

def save_server_config(guild_id, config):
    all_configs = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            all_configs = json.load(f)
    all_configs[str(guild_id)] = config
    with open(CONFIG_FILE, "w") as f:
        json.dump(all_configs, f, indent=4)

def load_payments():
    if os.path.exists(PAYMENTS_FILE):
        with open(PAYMENTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_payments(payments):
    with open(PAYMENTS_FILE, "w") as f:
        json.dump(payments, f, indent=4)

def create_payment_embed(payments):
    embed = discord.Embed(
        title="💰 Payment Tracker",
        description="Current payment balances",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    if not payments:
        embed.add_field(name="No Payments Yet", value="Use `!pay_add` to add payments", inline=False)
    else:
        sorted_payments = sorted(payments.items(), key=lambda x: x[1], reverse=True)
        for username, amount in sorted_payments:
            embed.add_field(name=f"👤 {username}", value=f"**${amount:,.2f}**", inline=True)
    embed.set_footer(text="Last updated")
    return embed

# -------------------------
# REMINDERS HELPERS
# -------------------------
def load_reminders():
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_reminders(reminders):
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=4)

# -------------------------
# WARNINGS HELPERS
# -------------------------
def load_warnings():
    if os.path.exists(WARNINGS_FILE):
        with open(WARNINGS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_warnings(data):
    with open(WARNINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def _warn_key(guild_id, user_id):
    return f"{guild_id}:{user_id}"

# -------------------------
# SCHEDULES HELPERS
# -------------------------
def load_schedules():
    if os.path.exists(SCHEDULES_FILE):
        with open(SCHEDULES_FILE, "r") as f:
            return json.load(f)
    return []

def save_schedules(data):
    with open(SCHEDULES_FILE, "w") as f:
        json.dump(data, f, indent=4)

# -------------------------
# TIME CONVERTER UTILITY
# -------------------------
def convert_time(time_str):
    """Converts 1h, 30m, 10s, 1d or combinations into total seconds"""
    time_regex = re.compile(r"(\d+)([smhd])")
    matches = time_regex.findall(time_str)
    total_seconds = 0
    for value, unit in matches:
        if unit == "s":   total_seconds += int(value)
        elif unit == "m": total_seconds += int(value) * 60
        elif unit == "h": total_seconds += int(value) * 3600
        elif unit == "d": total_seconds += int(value) * 86400
    return total_seconds

def format_duration(seconds):
    """Format seconds into a human-readable string"""
    seconds = int(seconds)
    days    = seconds // 86400
    hours   = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs    = seconds % 60
    parts   = []
    if days:    parts.append(f"{days}d")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if secs:    parts.append(f"{secs}s")
    return " ".join(parts) if parts else "0s"


# ==========================================================
# AUDIT LOG HELPER
# ==========================================================
async def get_audit_channel(guild: discord.Guild):
    config = load_server_config(guild.id)
    cid    = config.get("audit_log_channel_id")
    return guild.get_channel(int(cid)) if cid else None

async def send_audit(guild: discord.Guild, embed: discord.Embed):
    channel = await get_audit_channel(guild)
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[AuditLog] Could not send: {e}")


# ==========================================================
# TEMP-MUTE / TEMP-BAN SYSTEM
# ==========================================================
def load_tempmutes():
    if os.path.exists(TEMPMUTE_FILE):
        with open(TEMPMUTE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tempmutes(data):
    with open(TEMPMUTE_FILE, "w") as f:
        json.dump(data, f, indent=4)


@tasks.loop(seconds=15)
async def tempmute_checker():
    """Periodically check and lift expired temp-mutes."""
    data = load_tempmutes()
    now  = datetime.now(timezone.utc)
    changed = False
    to_remove = []
    for key, entry in data.items():
        unmute_time = datetime.fromisoformat(entry["unmute_at"])
        if now >= unmute_time:
            guild = bot.get_guild(int(entry["guild_id"]))
            if guild:
                member = guild.get_member(int(entry["user_id"]))
                muted_role = discord.utils.get(guild.roles, name="Muted")
                if member and muted_role and muted_role in member.roles:
                    try:
                        await member.remove_roles(muted_role, reason="Temp-mute expired")
                        print(f"[TempMute] Unmuted {member} in {guild.name}")
                    except Exception as e:
                        print(f"[TempMute] Could not unmute {entry['user_id']}: {e}")
            to_remove.append(key)
            changed = True
    for key in to_remove:
        del data[key]
    if changed:
        save_tempmutes(data)


async def ensure_muted_role(guild: discord.Guild) -> discord.Role:
    """Get or create the Muted role and apply channel overwrites."""
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if not muted_role:
        muted_role = await guild.create_role(name="Muted", reason="Auto-created for temp-mute system")
        for channel in guild.channels:
            try:
                await channel.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)
            except Exception:
                pass
    return muted_role


@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
    """Temporarily mute a member. Usage: !mute @user 10m Spamming"""
    seconds = convert_time(duration)
    if seconds == 0:
        return await ctx.send("❌ Invalid duration. Examples: `10m`, `1h`, `1d`")
    if seconds > 2592000:
        return await ctx.send("❌ Maximum mute duration is 30 days.")
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ You cannot mute someone with an equal or higher role.")

    muted_role = await ensure_muted_role(ctx.guild)
    if muted_role in member.roles:
        return await ctx.send(f"❌ {member.mention} is already muted.")

    await member.add_roles(muted_role, reason=f"Temp-muted by {ctx.author}: {reason}")

    unmute_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    data = load_tempmutes()
    data[f"{ctx.guild.id}-{member.id}"] = {
        "guild_id":  str(ctx.guild.id),
        "user_id":   str(member.id),
        "unmute_at": unmute_time.isoformat(),
        "reason":    reason,
        "muted_by":  str(ctx.author.id)
    }
    save_tempmutes(data)

    ts = int(unmute_time.timestamp())
    embed = discord.Embed(
        title="🔇 Member Muted",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 Member",   value=member.mention,            inline=True)
    embed.add_field(name="⏱️ Duration", value=format_duration(seconds),  inline=True)
    embed.add_field(name="📅 Unmute",   value=f"<t:{ts}:R>",             inline=True)
    embed.add_field(name="📋 Reason",   value=reason,                    inline=False)
    embed.set_footer(text=f"Muted by {ctx.author.display_name}")
    await ctx.send(embed=embed)
    await send_audit(ctx.guild, embed)

    try:
        dm_embed = discord.Embed(
            title="🔇 You've Been Muted",
            description=f"You were muted in **{ctx.guild.name}**.",
            color=discord.Color.orange()
        )
        dm_embed.add_field(name="⏱️ Duration", value=format_duration(seconds), inline=True)
        dm_embed.add_field(name="📅 Unmute",   value=f"<t:{ts}:R>",            inline=True)
        dm_embed.add_field(name="📋 Reason",   value=reason,                   inline=False)
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass


@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    """Manually unmute a member."""
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role or muted_role not in member.roles:
        return await ctx.send(f"❌ {member.mention} is not muted.")
    await member.remove_roles(muted_role, reason=f"Manually unmuted by {ctx.author}")
    data = load_tempmutes()
    key = f"{ctx.guild.id}-{member.id}"
    if key in data:
        del data[key]
        save_tempmutes(data)
    embed = discord.Embed(
        title="🔊 Member Unmuted",
        description=f"{member.mention} has been unmuted by {ctx.author.mention}.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command(name="tempban")
@commands.has_permissions(ban_members=True)
async def tempban(ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
    """Temporarily ban a member. Usage: !tempban @user 1d Breaking rules"""
    seconds = convert_time(duration)
    if seconds == 0:
        return await ctx.send("❌ Invalid duration. Examples: `1h`, `1d`, `7d`")
    if seconds > 2592000:
        return await ctx.send("❌ Maximum ban duration is 30 days.")
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ You cannot ban someone with an equal or higher role.")

    unban_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    ts = int(unban_time.timestamp())

    try:
        dm_embed = discord.Embed(
            title="🔨 You've Been Temporarily Banned",
            description=f"You were banned from **{ctx.guild.name}**.",
            color=discord.Color.red()
        )
        dm_embed.add_field(name="⏱️ Duration", value=format_duration(seconds), inline=True)
        dm_embed.add_field(name="📅 Unban",    value=f"<t:{ts}:F>",            inline=True)
        dm_embed.add_field(name="📋 Reason",   value=reason,                   inline=False)
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass

    await member.ban(reason=f"[TEMPBAN {format_duration(seconds)}] {reason} | by {ctx.author}")

    async def do_unban():
        await asyncio.sleep(seconds)
        try:
            bans = [ban async for ban in ctx.guild.bans()]
            banned_user = discord.utils.get(bans, user__id=member.id)
            if banned_user:
                await ctx.guild.unban(member, reason="Temp-ban expired")
                print(f"[TempBan] Unbanned {member} in {ctx.guild.name}")
        except Exception as e:
            print(f"[TempBan] Error unbanning {member.id}: {e}")

    bot.loop.create_task(do_unban())

    embed = discord.Embed(
        title="🔨 Member Temp-Banned",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 Member",   value=f"{member} ({member.id})",  inline=True)
    embed.add_field(name="⏱️ Duration", value=format_duration(seconds),   inline=True)
    embed.add_field(name="📅 Unban",    value=f"<t:{ts}:R>",              inline=True)
    embed.add_field(name="📋 Reason",   value=reason,                     inline=False)
    embed.set_footer(text=f"Banned by {ctx.author.display_name}")
    await ctx.send(embed=embed)
    await send_audit(ctx.guild, embed)


# ==========================================================
# WARNING SYSTEM
# ==========================================================
@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Warn a member. Escalating punishments apply automatically."""
    if member.bot:
        return await ctx.send("❌ You cannot warn a bot.")
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send("❌ You cannot warn someone with an equal or higher role.")

    data = load_warnings()
    key  = _warn_key(ctx.guild.id, member.id)
    if key not in data:
        data[key] = {"guild_id": str(ctx.guild.id), "user_id": str(member.id), "warns": []}

    data[key]["warns"].append({
        "reason":    reason,
        "warned_by": str(ctx.author.id),
        "warned_at": datetime.now(timezone.utc).isoformat(),
    })
    save_warnings(data)
    total = len(data[key]["warns"])

    embed = discord.Embed(
        title="⚠️ Member Warned",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="👤 Member",   value=member.mention, inline=True)
    embed.add_field(name="⚠️ Warn #",   value=str(total),     inline=True)
    embed.add_field(name="📋 Reason",   value=reason,         inline=False)
    embed.set_footer(text=f"Warned by {ctx.author.display_name}")
    await ctx.send(embed=embed)
    await send_audit(ctx.guild, embed)

    # DM the warned member
    try:
        dm = discord.Embed(
            title=f"⚠️ You've Been Warned in {ctx.guild.name}",
            color=discord.Color.orange(),
        )
        dm.add_field(name="📋 Reason",      value=reason,     inline=False)
        dm.add_field(name="⚠️ Total Warns", value=str(total), inline=True)
        next_thresh = next((c for c in sorted(WARN_THRESHOLDS) if c > total), None)
        if next_thresh:
            _, _, label = WARN_THRESHOLDS[next_thresh]
            dm.add_field(name="⚡ Next Action", value=f"At {next_thresh} warns: **{label}**", inline=True)
        await member.send(embed=dm)
    except discord.Forbidden:
        pass

    # Escalating punishment
    if total in WARN_THRESHOLDS:
        action, duration, label = WARN_THRESHOLDS[total]
        p_embed = discord.Embed(
            title=f"🚨 Auto-Punishment — {label.title()}",
            description=f"{member.mention} reached **{total} warnings**.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        if action == "mute" and duration:
            muted_role = await ensure_muted_role(ctx.guild)
            if muted_role not in member.roles:
                await member.add_roles(muted_role, reason=f"Auto-mute: {total} warnings")
            unmute_time = datetime.now(timezone.utc) + timedelta(seconds=duration)
            mute_data   = load_tempmutes()
            mute_data[f"{ctx.guild.id}-{member.id}"] = {
                "guild_id":  str(ctx.guild.id),
                "user_id":   str(member.id),
                "unmute_at": unmute_time.isoformat(),
                "reason":    f"Auto-mute ({total} warnings)",
                "muted_by":  str(bot.user.id),
            }
            save_tempmutes(mute_data)
            ts = int(unmute_time.timestamp())
            p_embed.add_field(name="⏱️ Duration", value=format_duration(duration), inline=True)
            p_embed.add_field(name="📅 Unmute",   value=f"<t:{ts}:R>",             inline=True)
        elif action == "kick":
            try:
                await member.kick(reason=f"Auto-kick: {total} warnings")
            except discord.Forbidden:
                p_embed.add_field(name="❌ Error", value="Missing permissions to kick.", inline=False)
        elif action == "ban":
            try:
                await member.ban(reason=f"Auto-ban: {total} warnings")
            except discord.Forbidden:
                p_embed.add_field(name="❌ Error", value="Missing permissions to ban.", inline=False)

        await ctx.send(embed=p_embed)
        await send_audit(ctx.guild, p_embed)


@bot.command(name="warnings")
async def warnings(ctx, member: discord.Member = None):
    """View warnings for a member. Defaults to yourself."""
    target = member or ctx.author
    if member and member != ctx.author and not ctx.author.guild_permissions.manage_messages:
        return await ctx.send("❌ You don't have permission to view other members' warnings.")

    data  = load_warnings()
    key   = _warn_key(ctx.guild.id, target.id)
    warns = data.get(key, {}).get("warns", [])

    embed = discord.Embed(
        title=f"⚠️ Warnings — {target.display_name}",
        color=discord.Color.orange() if warns else discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    if not warns:
        embed.description = f"✅ {target.mention} has no warnings."
    else:
        embed.description = f"{target.mention} has **{len(warns)}** warning(s)."
        for i, w in enumerate(warns[-10:], 1):
            ts = int(datetime.fromisoformat(w["warned_at"]).timestamp())
            embed.add_field(
                name=f"⚠️ Warning #{i}",
                value=f"**Reason:** {w['reason']}\n**When:** <t:{ts}:R>",
                inline=False,
            )
        next_thresh = next((c for c in sorted(WARN_THRESHOLDS) if c > len(warns)), None)
        if next_thresh:
            _, _, label = WARN_THRESHOLDS[next_thresh]
            embed.add_field(name="⚡ Next Threshold", value=f"At **{next_thresh}** warns: **{label}**", inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="clearwarns")
@commands.has_permissions(manage_messages=True)
async def clearwarns(ctx, member: discord.Member, index: int = None):
    """Clear warnings. !clearwarns @user = all | !clearwarns @user 2 = specific"""
    data = load_warnings()
    key  = _warn_key(ctx.guild.id, member.id)
    if key not in data or not data[key]["warns"]:
        return await ctx.send(f"✅ {member.mention} has no warnings to clear.")
    if index is None:
        count = len(data[key]["warns"])
        data[key]["warns"] = []
        save_warnings(data)
        await ctx.send(f"✅ Cleared all **{count}** warning(s) for {member.mention}.")
    else:
        warns = data[key]["warns"]
        if index < 1 or index > len(warns):
            return await ctx.send(f"❌ Invalid index. {member.mention} has {len(warns)} warning(s).")
        removed = warns.pop(index - 1)
        save_warnings(data)
        await ctx.send(f"✅ Removed warning #{index} (`{removed['reason']}`) from {member.mention}.")


# ==========================================================
# SLOWMODE COMMAND
# ==========================================================
@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, time_str: str = "0", channel: discord.TextChannel = None):
    """
    Set slowmode. Usage:
      !slowmode 30s           — current channel
      !slowmode 5m #general   — specific channel
      !slowmode off           — disable
    Max: 6 hours (21600s).
    """
    target = channel or ctx.channel
    if time_str.lower() in ("off", "0", "disable"):
        seconds = 0
    else:
        seconds = convert_time(time_str)
        if seconds == 0:
            return await ctx.send("❌ Invalid time. Examples: `10s`, `30s`, `5m`, `1h` or `off`")
        if seconds > 21600:
            return await ctx.send("❌ Discord's maximum slowmode is 6 hours (21600s).")

    await target.edit(slowmode_delay=seconds)

    if seconds == 0:
        embed = discord.Embed(
            title="✅ Slowmode Disabled",
            description=f"Slowmode has been turned off in {target.mention}.",
            color=discord.Color.green(),
        )
    else:
        embed = discord.Embed(
            title="🐢 Slowmode Enabled",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="💬 Channel",  value=target.mention,           inline=True)
        embed.add_field(name="⏱️ Interval", value=format_duration(seconds), inline=True)
        embed.set_footer(text=f"Set by {ctx.author.display_name}")

    await ctx.send(embed=embed)

    audit_embed = discord.Embed(
        title="🐢 Slowmode Changed",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    audit_embed.add_field(name="💬 Channel", value=target.mention, inline=True)
    audit_embed.add_field(name="⏱️ Delay",   value=format_duration(seconds) if seconds else "Off", inline=True)
    audit_embed.add_field(name="👤 Set By",  value=ctx.author.mention, inline=True)
    await send_audit(ctx.guild, audit_embed)


# ==========================================================
# SCHEDULED ANNOUNCEMENTS
# ==========================================================
@tasks.loop(seconds=30)
async def scheduled_announcements_loop():
    schedules = load_schedules()
    now       = datetime.now(timezone.utc)
    remaining = []
    changed   = False
    for item in schedules:
        fire_time = datetime.fromisoformat(item["fire_at"])
        if now >= fire_time:
            try:
                guild   = bot.get_guild(int(item["guild_id"]))
                channel = guild.get_channel(int(item["channel_id"])) if guild else None
                if channel:
                    embed = discord.Embed(
                        title="📢 Scheduled Announcement",
                        description=item["message"],
                        color=discord.Color.blue(),
                        timestamp=now,
                    )
                    embed.set_footer(text=f"Scheduled by {item['author_name']}")
                    mention = "@everyone" if item.get("mention_everyone") else None
                    await channel.send(content=mention, embed=embed)
            except Exception as e:
                print(f"[Schedule] Error firing announcement: {e}")
            changed = True
        else:
            remaining.append(item)
    if changed:
        save_schedules(remaining)


@bot.command(name="schedule")
@commands.has_permissions(administrator=True)
async def schedule(ctx, channel: discord.TextChannel, time_str: str, *, message: str):
    """
    Schedule an announcement.
    Usage: !schedule #channel 2h Your message here
    Add --everyone at the end to ping @everyone.
    """
    mention_everyone = False
    if message.endswith("--everyone"):
        mention_everyone = True
        message = message[:-len("--everyone")].strip()

    seconds = convert_time(time_str)
    if seconds == 0:
        return await ctx.send("❌ Invalid time format. Examples: `30m`, `2h`, `1d`, `1h30m`")
    if seconds < 30:
        return await ctx.send("❌ Minimum schedule time is 30 seconds.")
    if seconds > 2592000:
        return await ctx.send("❌ Maximum schedule time is 30 days.")

    fire_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    ts      = int(fire_at.timestamp())

    schedules = load_schedules()
    schedules.append({
        "guild_id":         str(ctx.guild.id),
        "channel_id":       str(channel.id),
        "message":          message,
        "fire_at":          fire_at.isoformat(),
        "author_name":      ctx.author.display_name,
        "mention_everyone": mention_everyone,
    })
    save_schedules(schedules)

    embed = discord.Embed(
        title="📅 Announcement Scheduled",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="📢 Channel", value=channel.mention,          inline=True)
    embed.add_field(name="⏱️ In",      value=format_duration(seconds), inline=True)
    embed.add_field(name="🕐 Fire At", value=f"<t:{ts}:F>",            inline=True)
    embed.add_field(name="📝 Message", value=message[:500],            inline=False)
    if mention_everyone:
        embed.add_field(name="📣 Mention", value="@everyone will be pinged", inline=False)
    embed.set_footer(text=f"Scheduled by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="schedule_list")
@commands.has_permissions(administrator=True)
async def schedule_list(ctx):
    """List all pending scheduled announcements for this server."""
    schedules   = load_schedules()
    guild_items = [s for s in schedules if s["guild_id"] == str(ctx.guild.id)]
    if not guild_items:
        return await ctx.send("📭 No scheduled announcements for this server.")
    embed = discord.Embed(
        title="📅 Scheduled Announcements",
        description=f"**{len(guild_items)}** pending announcement(s)",
        color=discord.Color.blurple(),
    )
    for i, item in enumerate(guild_items[:10], 1):
        ts      = int(datetime.fromisoformat(item["fire_at"]).timestamp())
        channel = ctx.guild.get_channel(int(item["channel_id"]))
        embed.add_field(
            name=f"#{i} — <t:{ts}:R>",
            value=f"**Channel:** {channel.mention if channel else 'Unknown'}\n**Message:** {item['message'][:80]}",
            inline=False,
        )
    await ctx.send(embed=embed)


@bot.command(name="schedule_cancel")
@commands.has_permissions(administrator=True)
async def schedule_cancel(ctx, index: int):
    """Cancel a scheduled announcement by its list number (from !schedule_list)."""
    schedules   = load_schedules()
    guild_items = [s for s in schedules if s["guild_id"] == str(ctx.guild.id)]
    if index < 1 or index > len(guild_items):
        return await ctx.send("❌ Invalid index. Use `!schedule_list` to see pending announcements.")
    target = guild_items[index - 1]
    schedules.remove(target)
    save_schedules(schedules)
    await ctx.send(f"✅ Scheduled announcement #{index} has been cancelled.")


# ==========================================================
# AUDIT LOG SETUP COMMAND
# ==========================================================
@bot.command(name="setauditlog")
@commands.has_permissions(administrator=True)
async def setauditlog(ctx, channel: discord.TextChannel = None):
    """Set or view the audit log channel. Usage: !setauditlog #channel"""
    config = load_server_config(ctx.guild.id)
    if channel is None:
        current_id = config.get("audit_log_channel_id")
        if current_id:
            ch = ctx.guild.get_channel(int(current_id))
            return await ctx.send(f"📋 Audit log channel: {ch.mention if ch else f'ID {current_id} (not found)'}.")
        return await ctx.send("❌ No audit log channel set. Use `!setauditlog #channel`.")

    config["audit_log_channel_id"] = str(channel.id)
    save_server_config(ctx.guild.id, config)
    embed = discord.Embed(
        title="✅ Audit Log Channel Set",
        description=f"Server events will now be logged to {channel.mention}.",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="📋 What gets logged",
        value=(
            "• ✏️ Message edits (before & after)\n"
            "• 🗑️ Message deletes\n"
            "• 📥 Member joins & 📤 leaves\n"
            "• 🎭 Role changes & ✏️ nickname changes\n"
            "• 🔨 Bans & Unbans\n"
            "• 🐢 Slowmode changes\n"
            "• ⚠️ Warnings & auto-punishments\n"
            "• 🔇 Mutes & Temp-bans"
        ),
        inline=False,
    )
    await ctx.send(embed=embed)


# ==========================================================
# AFK SYSTEM
# ==========================================================
def load_afk():
    if os.path.exists(AFK_FILE):
        with open(AFK_FILE, "r") as f:
            return json.load(f)
    return {}

def save_afk(data):
    with open(AFK_FILE, "w") as f:
        json.dump(data, f, indent=4)


@bot.command(name="afk")
async def afk(ctx, *, reason: str = "AFK"):
    """Set yourself as AFK. The bot will reply when someone pings you."""
    afk_data = load_afk()
    afk_data[str(ctx.author.id)] = {
        "reason":   reason,
        "set_at":   datetime.now(timezone.utc).isoformat(),
        "guild_id": str(ctx.guild.id)
    }
    save_afk(afk_data)
    embed = discord.Embed(
        title="💤 AFK Set",
        description=f"{ctx.author.mention} is now AFK.\n**Reason:** {reason}",
        color=discord.Color.light_grey()
    )
    embed.set_footer(text="You'll be removed from AFK when you send a message.")
    await ctx.send(embed=embed)
    try:
        if not ctx.author.display_name.startswith("[AFK]"):
            await ctx.author.edit(nick=f"[AFK] {ctx.author.display_name[:28]}")
    except discord.Forbidden:
        pass


# ==========================================================
# CUSTOM COMMANDS SYSTEM
# ==========================================================
def load_custom_commands():
    if os.path.exists(CUSTOM_COMMANDS_FILE):
        with open(CUSTOM_COMMANDS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_custom_commands(data):
    with open(CUSTOM_COMMANDS_FILE, "w") as f:
        json.dump(data, f, indent=4)


@bot.command(name="addcmd")
@commands.has_permissions(administrator=True)
async def addcmd(ctx, command_name: str, *, response: str):
    """Add a custom command. Usage: !addcmd discord Join us at discord.gg/example"""
    command_name = command_name.lower().lstrip("!")
    builtin = {c.name for c in bot.commands}
    if command_name in builtin:
        return await ctx.send(f"❌ `!{command_name}` is a built-in command and cannot be overridden.")
    data = load_custom_commands()
    guild_str = str(ctx.guild.id)
    if guild_str not in data:
        data[guild_str] = {}
    data[guild_str][command_name] = {
        "response":   response,
        "created_by": str(ctx.author.id),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    save_custom_commands(data)
    embed = discord.Embed(title="✅ Custom Command Added", color=discord.Color.green())
    embed.add_field(name="Command",  value=f"`!{command_name}`", inline=True)
    embed.add_field(name="Response", value=response[:200],       inline=False)
    await ctx.send(embed=embed)


@bot.command(name="removecmd")
@commands.has_permissions(administrator=True)
async def removecmd(ctx, command_name: str):
    """Remove a custom command."""
    command_name = command_name.lower().lstrip("!")
    data = load_custom_commands()
    guild_str = str(ctx.guild.id)
    if guild_str not in data or command_name not in data[guild_str]:
        return await ctx.send(f"❌ No custom command `!{command_name}` found.")
    del data[guild_str][command_name]
    save_custom_commands(data)
    await ctx.send(f"✅ Custom command `!{command_name}` has been removed.")


@bot.command(name="listcmds")
async def listcmds(ctx):
    """List all custom commands for this server."""
    data = load_custom_commands()
    guild_str = str(ctx.guild.id)
    cmds = data.get(guild_str, {})
    if not cmds:
        return await ctx.send("📭 No custom commands set up for this server. Use `!addcmd` to add one.")
    embed = discord.Embed(
        title="📋 Custom Commands",
        description=f"This server has **{len(cmds)}** custom command(s).",
        color=discord.Color.blurple()
    )
    for name, info in cmds.items():
        embed.add_field(name=f"`!{name}`", value=info["response"][:100], inline=False)
    await ctx.send(embed=embed)


# ==========================================================
# UPTIME COMMAND
# ==========================================================
@bot.command(name="uptime")
async def uptime(ctx):
    """Show how long the bot has been running."""
    elapsed = time.time() - BOT_START_TIME
    embed = discord.Embed(
        title="⏱️ Bot Uptime",
        description=f"The bot has been online for **{format_duration(elapsed)}**.",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🕐 Started", value=f"<t:{int(BOT_START_TIME)}:F>", inline=True)
    embed.add_field(name="🏓 Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


# ==========================================================
# WELCOME IMAGE SYSTEM
# ==========================================================
async def generate_welcome_image(member: discord.Member) -> io.BytesIO | None:
    """Generate a welcome banner using Pillow."""
    if not PILLOW_AVAILABLE:
        return None
    try:
        W, H = 900, 300
        img = Image.new("RGBA", (W, H), (30, 30, 47, 255))
        draw = ImageDraw.Draw(img)
        for i in range(H):
            alpha = int(80 * (i / H))
            draw.line([(0, i), (W, i)], fill=(88, 101, 242, alpha))
        draw.rectangle([2, 2, W - 3, H - 3], outline=(88, 101, 242, 200), width=3)
        avatar_size = 160
        avatar_data = await member.display_avatar.with_size(256).read()
        avatar_img  = Image.open(io.BytesIO(avatar_data)).convert("RGBA").resize((avatar_size, avatar_size))
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, avatar_size, avatar_size], fill=255)
        avatar_img.putalpha(mask)
        border_size = avatar_size + 8
        border_img  = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
        ImageDraw.Draw(border_img).ellipse([0, 0, border_size, border_size], fill=(88, 101, 242, 255))
        border_x = 60
        border_y = (H - border_size) // 2
        img.paste(border_img, (border_x, border_y), border_img)
        img.paste(avatar_img, (border_x + 4, border_y + 4), avatar_img)
        text_x = border_x + border_size + 30
        try:
            font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_med   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      28)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      22)
        except Exception:
            font_big = font_med = font_small = ImageFont.load_default()
        draw.text((text_x, 70),  "WELCOME", font=font_big, fill=(88, 101, 242, 255))
        name = member.display_name[:24] + ("…" if len(member.display_name) > 24 else "")
        draw.text((text_x, 130), name, font=font_med, fill=(255, 255, 255, 230))
        draw.text((text_x, 175), f"Member #{member.guild.member_count}", font=font_small, fill=(185, 187, 190, 200))
        draw.text((text_x, 210), member.guild.name[:40], font=font_small, fill=(130, 140, 160, 200))
        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output
    except Exception as e:
        print(f"[WelcomeImage] Error generating image: {e}")
        return None


# ==========================================================
# KICK LIVE ANNOUNCEMENT SYSTEM
# ==========================================================
KICK_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://kick.com/",
    "Origin":          "https://kick.com",
    "DNT":             "1",
}
kick_live_states = {}


class LiveChannelSelect(Select):
    def __init__(self, guild: discord.Guild, kick_username: str, category: str):
        self.kick_username = kick_username
        self.category = category
        text_channels = [ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages][:25]
        options = [discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)) for ch in text_channels]
        super().__init__(placeholder="Select announcement channel...", min_values=1, max_values=1,
                         options=options, custom_id="live_channel_select")

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
        now = datetime.now(timezone.utc)
        embed = discord.Embed(title=f"🔴  {self.kick_username} is LIVE", color=0x53FC18, timestamp=now)
        embed.add_field(name="🎮 Category", value=self.category, inline=True)
        embed.add_field(name="📺 Platform", value="Kick.com", inline=True)
        embed.add_field(name="🔗 Stream Link",
                        value=f"[**Watch Now → kick.com/{self.kick_username}**](https://kick.com/{self.kick_username})",
                        inline=False)
        embed.set_footer(text=f"Went live • {now.strftime('%B %d, %Y at %I:%M %p UTC')}")
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="▶  Watch Stream", url=f"https://kick.com/{self.kick_username}",
                                        style=discord.ButtonStyle.link))
        await channel.send("@everyone", embed=embed, view=view)
        await interaction.response.edit_message(content=f"✅ Live announcement posted in {channel.mention}!",
                                                 embed=None, view=None)


class LiveCategorySelect(Select):
    def __init__(self, kick_username: str):
        self.kick_username = kick_username
        options = [
            discord.SelectOption(label="🎰 Slots & Casino",  value="Slots & Casino"),
            discord.SelectOption(label="🃏 Cases & Packs",   value="Cases & Packs"),
            discord.SelectOption(label="🎮 Just Chatting",   value="Just Chatting"),
            discord.SelectOption(label="🎯 Sports Betting",  value="Sports Betting"),
            discord.SelectOption(label="🎲 Gambling",        value="Gambling"),
            discord.SelectOption(label="🕹️ Gaming",          value="Gaming"),
            discord.SelectOption(label="🎵 Music",           value="Music"),
            discord.SelectOption(label="🎙️ Podcast / IRL",   value="Podcast / IRL"),
            discord.SelectOption(label="⚽ Sports",          value="Sports"),
            discord.SelectOption(label="📦 Unboxing",        value="Unboxing"),
        ]
        super().__init__(placeholder="Select your stream category...", min_values=1, max_values=1,
                         options=options, custom_id="live_category_select")

    async def callback(self, interaction: discord.Interaction):
        selected_category = self.values[0]
        view = discord.ui.View(timeout=120)
        view.add_item(LiveChannelSelect(interaction.guild, self.kick_username, selected_category))
        embed = discord.Embed(
            title="📺 Step 3 — Choose Announcement Channel",
            description=f"**Category:** {selected_category}\n\nWhich channel should the live notification go to?",
            color=0x53FC18
        )
        await interaction.response.edit_message(embed=embed, view=view)


class LiveKickUsernameModal(Modal, title="🔴 Go Live — Kick Username"):
    kick_username = TextInput(label="Your Kick.com Username", placeholder="e.g. NotLilKev",
                              max_length=50, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.kick_username.value.strip().lstrip("@")
        if not username:
            return await interaction.response.send_message("❌ Username cannot be empty.", ephemeral=True)
        view = discord.ui.View(timeout=120)
        view.add_item(LiveCategorySelect(username))
        embed = discord.Embed(
            title="📺 Step 2 — Select Your Category",
            description=f"**Kick Channel:** kick.com/{username}\n\nWhat category are you streaming in?",
            color=0x53FC18
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.command(name="live")
async def live(ctx: commands.Context):
    allowed_roles = {"Moderator", "Developer", "Support", "Owner", "Streamer"}
    author_roles  = {r.name for r in ctx.author.roles}
    is_admin      = ctx.author.guild_permissions.administrator
    if not is_admin and not (author_roles & allowed_roles):
        return await ctx.send("❌ You don't have permission to use this command.", delete_after=8)
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    class OpenLiveModal(View):
        def __init__(self):
            super().__init__(timeout=60)
        @discord.ui.button(label="🔴  Set Up Live Announcement", style=discord.ButtonStyle.success)
        async def open_modal(self, interaction: discord.Interaction, button: Button):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("❌ This panel isn't for you.", ephemeral=True)
            await interaction.response.send_modal(LiveKickUsernameModal())

    embed = discord.Embed(
        title="🔴 Go Live",
        description="Click the button below to set up your live announcement.",
        color=0x53FC18
    )
    embed.set_footer(text="Only visible to you")
    await ctx.send(embed=embed, view=OpenLiveModal(), delete_after=60)


# ==========================================================
# BACKGROUND TASKS
# ==========================================================
@tasks.loop(minutes=30)
async def keep_alive():
    print("[KeepAlive] Sending heartbeat ping to Discord...")
    try:
        await bot.wait_until_ready()
        await bot.fetch_user(bot.user.id)
    except Exception as e:
        print(f"[KeepAlive] Failed to ping: {e}")

@tasks.loop(minutes=10)
async def update_stats():
    for guild in bot.guilds:
        config = load_server_config(guild.id)
        stats_channel_id = config.get("stats_channel_id")
        if stats_channel_id:
            channel = guild.get_channel(stats_channel_id)
            if channel:
                try:
                    await channel.edit(name=f"📊 Members: {guild.member_count}")
                except Exception as e:
                    print(f"[Stats] Error updating channel in {guild.name}: {e}")

@tasks.loop(seconds=30)
async def reminder_loop():
    reminders = load_reminders()
    now       = datetime.now(timezone.utc)
    remaining = []
    for reminder in reminders:
        due_time = datetime.fromisoformat(reminder["due"])
        if now >= due_time:
            try:
                user  = await bot.fetch_user(reminder["user_id"])
                embed = discord.Embed(
                    title="⏰ Reminder!",
                    description=reminder["message"],
                    color=discord.Color.blurple(),
                    timestamp=now
                )
                embed.set_footer(text="This reminder was set by you")
                await user.send(embed=embed)
            except Exception as e:
                print(f"[Reminders] Could not send reminder: {e}")
        else:
            remaining.append(reminder)
    save_reminders(remaining)


@tasks.loop(minutes=15)
async def ticket_idle_checker():
    """Auto-close tickets where the opener hasn't replied in TICKET_IDLE_HOURS hours."""
    now      = datetime.now(timezone.utc)
    idle_for = timedelta(hours=TICKET_IDLE_HOURS)
    to_close = []

    for channel_id, entry in list(TICKET_ACTIVITY.items()):
        last_msg = entry.get("last_opener_message")
        if last_msg and (now - last_msg) >= idle_for:
            to_close.append((channel_id, entry["opener_id"]))

    for channel_id, opener_id in to_close:
        for guild in bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                await _auto_close_ticket(channel, opener_id)
                break


async def _auto_close_ticket(channel: discord.TextChannel, opener_id: int):
    """Close a ticket due to opener inactivity."""
    try:
        embed = discord.Embed(
            title="🔒 Ticket Auto-Closed",
            description=(
                f"This ticket was automatically closed because <@{opener_id}> "
                f"hasn't replied in **{TICKET_IDLE_HOURS} hours**."
            ),
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Auto-close system")
        await channel.send(embed=embed)

        ticket_number = channel.name.split("-")[-1]
        ticket_data   = load_ticket_data()
        for guild_str, gdata in ticket_data.items():
            ticket_key = f"ticket-{ticket_number}"
            if ticket_key in gdata.get("tickets", {}):
                gdata["tickets"][ticket_key]["status"]    = "closed"
                gdata["tickets"][ticket_key]["closed_at"] = datetime.now(timezone.utc).isoformat()
                gdata["tickets"][ticket_key]["closed_by"] = "auto-close"
        save_ticket_data(ticket_data)

        try:
            member = channel.guild.get_member(opener_id)
            if member:
                dm = discord.Embed(
                    title="🔒 Your Ticket Was Auto-Closed",
                    description=(
                        f"Your ticket in **{channel.guild.name}** was automatically closed because "
                        f"you hadn't replied in **{TICKET_IDLE_HOURS} hours**.\n\n"
                        "Open a new ticket any time you need help!"
                    ),
                    color=discord.Color.orange(),
                )
                await member.send(embed=dm)
        except Exception:
            pass

        await asyncio.sleep(5)
        await channel.delete(reason="Auto-closed: opener inactivity")
        if channel.id in TICKET_ACTIVITY:
            del TICKET_ACTIVITY[channel.id]
    except Exception as e:
        print(f"[TicketAutoClose] Error closing {channel.name}: {e}")


def register_ticket_for_autoclose(channel_id: int, opener_id: int):
    """Register a ticket channel for idle tracking."""
    TICKET_ACTIVITY[channel_id] = {
        "opener_id":           opener_id,
        "last_opener_message": datetime.now(timezone.utc),
    }


# -------------------------
# BOT EVENTS
# -------------------------
@bot.event
async def on_disconnect():
    print("[WARNING] Bot disconnected from Discord...")

@bot.event
async def on_resumed():
    print("[INFO] Bot reconnected to Discord.")

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="DaSixBot | Hosting"))
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} servers")
    keep_alive.start()
    update_stats.start()
    reminder_loop.start()
    tempmute_checker.start()
    scheduled_announcements_loop.start()
    ticket_idle_checker.start()
    print("[Bot] All background tasks started")


# -------------------------
# AUDIT LOG EVENTS
# -------------------------
@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild:
        return
    if before.content == after.content:
        return
    embed = discord.Embed(
        title="✏️ Message Edited",
        color=discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    embed.add_field(name="👤 User",    value=before.author.mention,  inline=True)
    embed.add_field(name="💬 Channel", value=before.channel.mention, inline=True)
    embed.add_field(name="🔗 Jump",    value=f"[Go to message]({after.jump_url})", inline=True)
    embed.add_field(name="📄 Before",  value=before.content[:1000] or "*empty*", inline=False)
    embed.add_field(name="📄 After",   value=after.content[:1000]  or "*empty*", inline=False)
    embed.set_footer(text=f"User ID: {before.author.id}")
    await send_audit(before.guild, embed)


@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    embed = discord.Embed(
        title="🗑️ Message Deleted",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    embed.add_field(name="👤 User",    value=message.author.mention,  inline=True)
    embed.add_field(name="💬 Channel", value=message.channel.mention, inline=True)
    embed.add_field(name="📄 Content", value=message.content[:1000] or "*no text content*", inline=False)
    if message.attachments:
        embed.add_field(name="📎 Attachments",
                        value="\n".join(a.filename for a in message.attachments), inline=False)
    embed.set_footer(text=f"User ID: {message.author.id}")
    await send_audit(message.guild, embed)


@bot.event
async def on_member_remove(member):
    roles = [r.name for r in member.roles if r.name != "@everyone"]
    embed = discord.Embed(
        title="📤 Member Left",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.add_field(name="👤 User",  value=f"{member} ({member.id})",               inline=True)
    embed.add_field(name="🏷️ Roles", value=", ".join(roles) if roles else "None",   inline=False)
    embed.set_footer(text=f"Members remaining: {member.guild.member_count}")
    await send_audit(member.guild, embed)


@bot.event
async def on_member_update(before, after):
    if not before.guild:
        return
    added   = [r for r in after.roles  if r not in before.roles]
    removed = [r for r in before.roles if r not in after.roles]
    if added or removed:
        embed = discord.Embed(
            title="🎭 Member Roles Updated",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        embed.add_field(name="👤 User", value=after.mention, inline=True)
        if added:
            embed.add_field(name="➕ Roles Added",   value=" ".join(r.mention for r in added),   inline=False)
        if removed:
            embed.add_field(name="➖ Roles Removed", value=" ".join(r.mention for r in removed), inline=False)
        embed.set_footer(text=f"User ID: {after.id}")
        await send_audit(after.guild, embed)
    if before.nick != after.nick:
        embed = discord.Embed(
            title="✏️ Nickname Changed",
            color=discord.Color.light_grey(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        embed.add_field(name="👤 User",   value=after.mention,              inline=True)
        embed.add_field(name="📄 Before", value=before.nick or "*none*",    inline=True)
        embed.add_field(name="📄 After",  value=after.nick  or "*removed*", inline=True)
        embed.set_footer(text=f"User ID: {after.id}")
        await send_audit(after.guild, embed)


@bot.event
async def on_member_ban(guild, user):
    embed = discord.Embed(
        title="🔨 Member Banned",
        color=discord.Color.dark_red(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{user} ({user.id})", inline=True)
    embed.set_footer(text=f"User ID: {user.id}")
    await send_audit(guild, embed)


@bot.event
async def on_member_unban(guild, user):
    embed = discord.Embed(
        title="✅ Member Unbanned",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{user} ({user.id})", inline=True)
    embed.set_footer(text=f"User ID: {user.id}")
    await send_audit(guild, embed)


# -------------------------
# ANTI-SPAM & MESSAGE HANDLER
# -------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    if not message.guild:
        await bot.process_commands(message)
        return

    user_id = message.author.id

    # ── Ticket opener activity tracking ──
    if message.channel.id in TICKET_ACTIVITY:
        entry = TICKET_ACTIVITY[message.channel.id]
        if message.author.id == entry["opener_id"]:
            entry["last_opener_message"] = datetime.now(timezone.utc)

    # ── AFK: remove AFK when the user sends a message ──
    afk_data = load_afk()
    if str(user_id) in afk_data:
        del afk_data[str(user_id)]
        save_afk(afk_data)
        try:
            nick = message.author.display_name
            if nick.startswith("[AFK] "):
                await message.author.edit(nick=nick[6:])
        except discord.Forbidden:
            pass
        try:
            await message.channel.send(
                f"👋 Welcome back {message.author.mention}, your AFK has been removed!", delete_after=8
            )
        except Exception:
            pass

    # ── AFK: notify sender if they pinged an AFK user ──
    for mentioned in message.mentions:
        if str(mentioned.id) in afk_data:
            info   = afk_data[str(mentioned.id)]
            set_ts = int(datetime.fromisoformat(info["set_at"]).timestamp())
            await message.channel.send(
                f"💤 {mentioned.display_name} is AFK — **{info['reason']}** (since <t:{set_ts}:R>)",
                delete_after=12
            )

    # ── Anti-spam ──
    if anti_spam.is_user_muted(user_id):
        try:
            await message.delete()
            remaining = anti_spam.get_mute_remaining(user_id)
            await message.channel.send(
                f"⏱️ {message.author.mention}, you're currently muted for spam. "
                f"You can send messages again in {int(remaining)} seconds.",
                delete_after=10
            )
        except discord.Forbidden:
            print(f"[AntiSpam] Could not delete message from {message.author}")
        return

    if anti_spam.add_message(user_id):
        anti_spam.mute_user(user_id)
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        try:
            embed = discord.Embed(
                title="⚠️ Spam Detected",
                description=(
                    "You've been temporarily muted for spamming.\n\n"
                    "**Reason:** Sending too many messages too quickly\n"
                    "**Duration:** 5 minutes\n\n"
                    "Please slow down and follow server rules."
                ),
                color=discord.Color.red()
            )
            await message.author.send(embed=embed)
        except discord.Forbidden:
            pass
        mod_role = discord.utils.get(message.guild.roles, name="Moderator")
        if mod_role:
            try:
                embed = discord.Embed(
                    title="🚨 Spam Alert",
                    description=(
                        f"**User:** {message.author.mention}\n"
                        f"**Channel:** {message.channel.mention}\n"
                        f"**Action:** User muted for 5 minutes\n"
                        f"**Time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    ),
                    color=discord.Color.orange()
                )
                await message.channel.send(embed=embed, delete_after=30)
            except Exception as e:
                print(f"[AntiSpam] Could not notify mods: {e}")
        return

    # ── Silent channel ──
    if message.channel.id in SILENT_CHANNELS:
        is_admin = message.author.guild_permissions.administrator
        if is_admin and message.guild.default_role in message.mentions:
            await bot.process_commands(message)
            return
        if is_admin and message.guild.default_role not in message.mentions:
            try:
                await message.edit(content=f"@everyone {message.content}")
            except discord.Forbidden:
                pass
            await bot.process_commands(message)
            return
        if message.guild.default_role in message.mentions or "@here" in message.content:
            try:
                content = message.content.replace("@everyone", "").replace("@here", "")
                await message.edit(content=content)
                try:
                    dm_embed = discord.Embed(
                        title="🔕 Notification Silenced",
                        description=f"Your message in {message.channel.mention} cannot ping @everyone.\n\nOnly admins can use @everyone in this channel.",
                        color=discord.Color.orange()
                    )
                    await message.author.send(embed=dm_embed)
                except discord.Forbidden:
                    pass
            except discord.Forbidden:
                pass
            await bot.process_commands(message)
            return

    # ── Verification code handling ──
    if message.author.id in PENDING_VERIFICATIONS:
        verification = PENDING_VERIFICATIONS[message.author.id]
        if message.channel.id == verification.get("channel_id"):
            code_input = message.content.strip()
            if len(code_input) == 6 and code_input.isdigit():
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
                if code_input == verification["code"]:
                    config = load_server_config(message.guild.id)
                    verified_role_id = config.get("verified_role_id")
                    if verified_role_id:
                        verified_role = message.guild.get_role(verified_role_id)
                        if verified_role:
                            await message.author.add_roles(verified_role)
                            verification_data = load_verifications()
                            account_analysis  = check_account_age(message.author)
                            verification_data[str(message.author.id)] = {
                                "verified_at":      datetime.now(timezone.utc).isoformat(),
                                "account_age_days": account_analysis["account_age_days"],
                                "risk_level":       account_analysis["risk_level"],
                                "guild_id":         str(message.guild.id),
                                "method":           "channel_code"
                            }
                            save_verifications(verification_data)
                            del PENDING_VERIFICATIONS[message.author.id]
                            success_msg = await message.channel.send(
                                f"✅ **{message.author.mention} Verification successful!** You now have access to the server."
                            )
                            await asyncio.sleep(5)
                            try:
                                await success_msg.delete()
                            except Exception:
                                pass
                            try:
                                welcome_embed = discord.Embed(
                                    title="✅ You're Now Verified!",
                                    description=(
                                        f"Welcome to **{message.guild.name}**! 🎉\n\n"
                                        "You now have full access to the server!\n\n"
                                        "If you need help, use the ticket system."
                                    ),
                                    color=discord.Color.green(),
                                    timestamp=datetime.now(timezone.utc)
                                )
                                await message.author.send(embed=welcome_embed)
                            except discord.Forbidden:
                                pass
                else:
                    verification["attempts"] += 1
                    if verification["attempts"] >= 3:
                        error_msg = await message.channel.send(
                            f"❌ **{message.author.mention}** Too many failed attempts. Please wait 5 minutes before requesting a new code."
                        )
                        del PENDING_VERIFICATIONS[message.author.id]
                    else:
                        error_msg = await message.channel.send(
                            f"❌ **{message.author.mention}** Incorrect code! Attempts remaining: {3 - verification['attempts']}"
                        )
                    await asyncio.sleep(5)
                    try:
                        await error_msg.delete()
                    except Exception:
                        pass

    # ── Custom commands ──
    if message.content.startswith("!"):
        cmd_name = message.content[1:].split()[0].lower()
        data = load_custom_commands()
        guild_cmds = data.get(str(message.guild.id), {})
        if cmd_name in guild_cmds:
            builtin = {c.name for c in bot.commands}
            if cmd_name not in builtin:
                await message.channel.send(guild_cmds[cmd_name]["response"])
                return

    await bot.process_commands(message)


# -------------------------
# Advanced Support Ticket System
# -------------------------
TICKET_DATA_FILE = "tickets.json"

def load_ticket_data():
    if os.path.exists(TICKET_DATA_FILE):
        with open(TICKET_DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_ticket_data(data):
    with open(TICKET_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_next_ticket_number(guild_id):
    ticket_data = load_ticket_data()
    guild_str = str(guild_id)
    if guild_str not in ticket_data:
        ticket_data[guild_str] = {"counter": 0, "tickets": {}}
    ticket_data[guild_str]["counter"] += 1
    save_ticket_data(ticket_data)
    return ticket_data[guild_str]["counter"]

async def generate_transcript(channel):
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Ticket Transcript - {channel_name}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #36393f; color: #dcddde; margin: 20px; }}
            .header {{ background: #202225; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .message {{ background: #40444b; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #7289da; }}
            .author {{ color: #7289da; font-weight: bold; }}
            .timestamp {{ color: #72767d; font-size: 12px; }}
            .content {{ margin-top: 8px; line-height: 1.5; }}
            .attachment {{ color: #00b0f4; text-decoration: none; display: block; margin-top: 5px; }}
            .system {{ background: #2f3136; border-left: 4px solid #faa61a; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Ticket Transcript: {channel_name}</h1>
            <p>Generated at: {timestamp}</p>
            <p>Total Messages: {message_count}</p>
        </div>
        <div class="messages">{messages}</div>
    </body>
    </html>
    """
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    message_html = ""
    for msg in messages:
        timestamp     = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
        message_class = "message system" if msg.author.bot else "message"
        attachments_html = ""
        if msg.attachments:
            for att in msg.attachments:
                attachments_html += f'<a class="attachment" href="{att.url}">📎 {att.filename}</a>'
        message_html += f"""
        <div class="{message_class}">
            <span class="author">{msg.author.name}</span>
            <span class="timestamp">{timestamp}</span>
            <div class="content">{msg.content}</div>
            {attachments_html}
        </div>
        """
    html_content = html_template.format(
        channel_name=channel.name,
        timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        message_count=len(messages),
        messages=message_html
    )
    return io.BytesIO(html_content.encode('utf-8'))


# -------------------------
# TICKET RATING SYSTEM
# -------------------------
class TicketRatingView(View):
    def __init__(self, ticket_number, guild_name):
        super().__init__(timeout=86400)
        self.ticket_number = ticket_number
        self.guild_name    = guild_name

    async def _record_rating(self, interaction: discord.Interaction, stars: int, label: str):
        ticket_data = load_ticket_data()
        for guild_str, guild_data in ticket_data.items():
            ticket_key = f"ticket-{self.ticket_number}"
            if ticket_key in guild_data.get("tickets", {}):
                guild_data["tickets"][ticket_key]["rating"]   = stars
                guild_data["tickets"][ticket_key]["rated_at"] = datetime.now(timezone.utc).isoformat()
                save_ticket_data(ticket_data)
                break
        embed = discord.Embed(
            title="⭐ Thanks for your feedback!",
            description=f"You rated your support experience **{label}** for ticket **#{self.ticket_number}** in **{self.guild_name}**.\n\nYour feedback helps us improve!",
            color=discord.Color.gold()
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⭐",       style=discord.ButtonStyle.secondary, custom_id="rate_1")
    async def rate_1(self, i, b): await self._record_rating(i, 1, "⭐ (1/5)")
    @discord.ui.button(label="⭐⭐",     style=discord.ButtonStyle.secondary, custom_id="rate_2")
    async def rate_2(self, i, b): await self._record_rating(i, 2, "⭐⭐ (2/5)")
    @discord.ui.button(label="⭐⭐⭐",   style=discord.ButtonStyle.secondary, custom_id="rate_3")
    async def rate_3(self, i, b): await self._record_rating(i, 3, "⭐⭐⭐ (3/5)")
    @discord.ui.button(label="⭐⭐⭐⭐",   style=discord.ButtonStyle.secondary, custom_id="rate_4")
    async def rate_4(self, i, b): await self._record_rating(i, 4, "⭐⭐⭐⭐ (4/5)")
    @discord.ui.button(label="⭐⭐⭐⭐⭐", style=discord.ButtonStyle.success,   custom_id="rate_5")
    async def rate_5(self, i, b): await self._record_rating(i, 5, "⭐⭐⭐⭐⭐ (5/5)")


TICKET_TEMPLATES = {
    "💰 General Support": (
        "**Please answer the following:**\n\n"
        "1. What is the issue you need help with?\n"
        "2. When did this start?\n"
        "3. Have you tried anything to resolve it?\n"
        "4. Any additional information?"
    ),
    "⚙️ Technical Support": (
        "**Please answer the following:**\n\n"
        "1. What is the technical problem?\n"
        "2. What device/OS are you using?\n"
        "3. What error message do you see (if any)?\n"
        "4. Steps you've already tried?\n"
        "5. Screenshots (attach below if possible)"
    ),
    "👤 Account Issues": (
        "**Please answer the following:**\n\n"
        "1. What account issue are you experiencing?\n"
        "2. Your Discord username/ID:\n"
        "3. When did this issue start?\n"
        "4. Have you contacted support before about this?"
    ),
    "📢 Report User/Issue": (
        "**Please answer the following:**\n\n"
        "1. Who are you reporting (username/ID)?\n"
        "2. What did they do?\n"
        "3. When did this happen?\n"
        "4. Do you have evidence? (screenshots, links — attach below)"
    ),
    "💡 Suggestion": (
        "**Please fill in the following:**\n\n"
        "1. What is your suggestion?\n"
        "2. Why would this benefit the server/community?\n"
        "3. Any examples from other servers or platforms?"
    ),
    "❓ General Question": (
        "**Please describe your question below:**\n\n"
        "1. What would you like to know?\n"
        "2. Have you checked the FAQ or rules already?\n"
        "3. Any other context that would help us answer?"
    ),
}


class TicketCategorySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="💰 General Support",   description="General questions and support",    emoji="💰"),
            discord.SelectOption(label="⚙️ Technical Support", description="Bot or server technical issues",   emoji="⚙️"),
            discord.SelectOption(label="👤 Account Issues",    description="Verification or account problems", emoji="👤"),
            discord.SelectOption(label="📢 Report User/Issue", description="Report a user or problem",         emoji="📢"),
            discord.SelectOption(label="💡 Suggestion",        description="Suggest improvements",             emoji="💡"),
            discord.SelectOption(label="❓ General Question",  description="General inquiry",                  emoji="❓"),
        ]
        super().__init__(placeholder="Select a ticket category...", min_values=1, max_values=1,
                         options=options, custom_id="ticket_category_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReportModal(self.values[0]))


class TicketControlsView(View):
    def __init__(self, ticket_number):
        super().__init__(timeout=None)
        self.ticket_number = ticket_number

    @discord.ui.button(label="✋ Claim", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim_callback(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Only staff can claim tickets.", ephemeral=True)
        embed = interaction.message.embeds[0]
        for field in embed.fields:
            if field.name == "👨‍💻 Claimed By":
                return await interaction.response.send_message("❌ This ticket is already claimed!", ephemeral=True)
        embed.color = discord.Color.gold()
        embed.add_field(name="👨‍💻 Claimed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="⏰ Claimed At",  value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:R>", inline=True)
        for i, field in enumerate(embed.fields):
            if field.name == "📝 Status":
                embed.set_field_at(i, name="📝 Status", value="🟡 Claimed", inline=True)
        embed.set_footer(text=f"Ticket #{self.ticket_number} | Status: CLAIMED")
        button.disabled = True
        button.label    = "✅ Claimed"
        button.style    = discord.ButtonStyle.success
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message(f"✅ {interaction.user.mention} has claimed this ticket!")
        ticket_data = load_ticket_data()
        guild_str   = str(interaction.guild.id)
        ticket_str  = f"ticket-{self.ticket_number}"
        if guild_str in ticket_data and ticket_str in ticket_data[guild_str].get("tickets", {}):
            ticket_data[guild_str]["tickets"][ticket_str]["claimed_by"] = str(interaction.user.id)
            ticket_data[guild_str]["tickets"][ticket_str]["claimed_at"] = datetime.now(timezone.utc).isoformat()
            save_ticket_data(ticket_data)

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_callback(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_messages:
            if str(interaction.user.id) not in (interaction.channel.topic or ""):
                return await interaction.response.send_message("❌ Only staff or the ticket owner can close this.", ephemeral=True)
        await interaction.response.send_message("🔒 Generating transcript and closing ticket...", ephemeral=True)
        html_transcript = await generate_transcript(interaction.channel)
        ticket_number   = interaction.channel.name.split("-")[-1]
        user_id         = interaction.channel.topic.split("ID: ")[-1] if interaction.channel.topic else "Unknown"
        ticket_data     = load_ticket_data()
        guild_str       = str(interaction.guild.id)
        ticket_str      = f"ticket-{ticket_number}"
        closed_at_iso   = datetime.now(timezone.utc).isoformat()
        if guild_str in ticket_data and ticket_str in ticket_data[guild_str].get("tickets", {}):
            tkt = ticket_data[guild_str]["tickets"][ticket_str]
            tkt["closed_by"] = str(interaction.user.id)
            tkt["closed_at"] = closed_at_iso
            tkt["status"]    = "closed"
            save_ticket_data(ticket_data)
        close_embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"**Ticket #{ticket_number}** has been closed.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        close_embed.add_field(name="Closed By", value=interaction.user.mention, inline=True)
        close_embed.add_field(name="Channel",   value=interaction.channel.name,  inline=True)
        mod_log_channel = discord.utils.get(interaction.guild.channels, name="ticket-logs")
        if mod_log_channel:
            html_transcript.seek(0)
            await mod_log_channel.send(
                embed=close_embed,
                file=discord.File(html_transcript, filename=f"ticket-{ticket_number}-transcript.html")
            )
        # Remove from idle tracking
        if interaction.channel.id in TICKET_ACTIVITY:
            del TICKET_ACTIVITY[interaction.channel.id]
        try:
            member = interaction.guild.get_member(int(user_id))
            if member:
                html_transcript.seek(0)
                dm_embed = discord.Embed(
                    title="Ticket Closed",
                    description=f"Your ticket **#{ticket_number}** in **{interaction.guild.name}** has been closed.\n\nThank you for contacting support!",
                    color=discord.Color.red()
                )
                await member.send(embed=dm_embed,
                                  file=discord.File(html_transcript, filename=f"ticket-{ticket_number}-transcript.html"))
                rating_embed = discord.Embed(
                    title="⭐ How was your support experience?",
                    description=f"Please rate your experience for ticket **#{ticket_number}** in **{interaction.guild.name}**.\n\nYour feedback helps us improve!",
                    color=discord.Color.gold()
                )
                await member.send(embed=rating_embed, view=TicketRatingView(ticket_number, interaction.guild.name))
        except Exception as e:
            print(f"[Ticket] Could not DM user after close: {e}")
        await asyncio.sleep(3)
        await interaction.channel.delete()

    @discord.ui.button(label="📋 Add User", style=discord.ButtonStyle.secondary, custom_id="add_user_ticket")
    async def add_user_callback(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Only staff can add users.", ephemeral=True)
        await interaction.response.send_modal(AddUserModal(interaction.channel))

    @discord.ui.button(label="⚠️ Priority", style=discord.ButtonStyle.secondary, custom_id="priority_ticket")
    async def priority_callback(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Only staff can change priority.", ephemeral=True)
        await interaction.response.send_message("Select new priority level:",
                                                 view=PrioritySelectView(interaction.message, self.ticket_number),
                                                 ephemeral=True)


class AddUserModal(Modal):
    def __init__(self, channel):
        super().__init__(title="Add User to Ticket")
        self.channel    = channel
        self.user_input = TextInput(label="User ID or @mention",
                                    placeholder="Enter user ID or mention them",
                                    style=discord.TextStyle.short)
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.user_input.value.strip().replace("<@", "").replace(">", "").replace("!", "")
        try:
            member = interaction.guild.get_member(int(raw))
            if member:
                await self.channel.set_permissions(member, read_messages=True, send_messages=True)
                await interaction.response.send_message(f"✅ Added {member.mention} to the ticket.", ephemeral=True)
                await self.channel.send(f"➕ {member.mention} has been added to this ticket by {interaction.user.mention}")
            else:
                await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID or mention.", ephemeral=True)


class PrioritySelectView(View):
    def __init__(self, message, ticket_number):
        super().__init__(timeout=60)
        self.message       = message
        self.ticket_number = ticket_number
        options = [
            discord.SelectOption(label="🟢 Low Priority",      value="low",      emoji="🟢"),
            discord.SelectOption(label="🟡 Medium Priority",   value="medium",   emoji="🟡"),
            discord.SelectOption(label="🟠 High Priority",     value="high",     emoji="🟠"),
            discord.SelectOption(label="🔴 Critical Priority", value="critical", emoji="🔴"),
        ]
        select          = Select(placeholder="Choose priority level", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        priority = interaction.data["values"][0]
        embed    = self.message.embeds[0]
        priority_display = {"low": "🟢 Low", "medium": "🟡 Medium", "high": "🟠 High", "critical": "🔴 Critical"}
        for i, field in enumerate(embed.fields):
            if field.name == "⚡ Priority":
                embed.set_field_at(i, name="⚡ Priority", value=priority_display[priority], inline=True)
        await self.message.edit(embed=embed)
        await interaction.response.send_message(f"✅ Priority updated to **{priority_display[priority]}**", ephemeral=True)
        await interaction.channel.send(f"⚠️ Ticket priority changed to **{priority_display[priority]}** by {interaction.user.mention}")


class ReportModal(Modal):
    def __init__(self, category):
        super().__init__(title=f"🎫 Create Ticket - {category[:40]}")
        self.category    = category
        self.issue_title = TextInput(label="Title", placeholder="Brief summary of your issue",
                                     max_length=100, style=discord.TextStyle.short)
        self.issue_details = TextInput(
            label="Details", style=discord.TextStyle.paragraph,
            placeholder="Please describe your issue in detail.",
            min_length=20, max_length=1000
        )
        self.add_item(self.issue_title)
        self.add_item(self.issue_details)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        for ch in guild.text_channels:
            if "ticket-" in ch.name and ch.topic and str(interaction.user.id) in ch.topic:
                return await interaction.response.send_message(
                    f"⚠️ You already have an open ticket: {ch.mention}", ephemeral=True
                )
        ticket_number = get_next_ticket_number(guild.id)
        category_obj  = discord.utils.get(guild.categories, name="📬 Support Tickets")
        if not category_obj:
            category_obj = await guild.create_category("📬 Support Tickets")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user:   discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_messages=True)
        }
        mod_role = discord.utils.get(guild.roles, name="Moderator")
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        ticket_channel = await guild.create_text_channel(
            f"ticket-{ticket_number}",
            category=category_obj,
            topic=f"Ticket #{ticket_number} | User: {interaction.user.name} | ID: {interaction.user.id}",
            overwrites=overwrites
        )

        # Register for auto-close idle tracking
        register_ticket_for_autoclose(ticket_channel.id, interaction.user.id)

        embed = discord.Embed(
            title=f"🎫 {self.issue_title.value}",
            description=f"**Category:** {self.category}\n**Opened By:** {interaction.user.mention} ({interaction.user.id})",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="⚡ Priority",      value="🟡 Medium",         inline=True)
        embed.add_field(name="📝 Status",        value="🔵 Open",           inline=True)
        embed.add_field(name="🎫 Ticket Number", value=f"#{ticket_number}", inline=True)
        embed.add_field(name="📋 Issue Details", value=f"```\n{self.issue_details.value[:500]}\n```", inline=False)
        embed.add_field(name="⏰ Auto-Close",    value=f"Closes after **{TICKET_IDLE_HOURS}h** of opener inactivity", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Ticket #{ticket_number} | Created")

        template_text = TICKET_TEMPLATES.get(self.category, "")
        welcome_msg = (
            f"{interaction.user.mention} Welcome to your support ticket!\n\n"
            "**What to expect:**\n"
            "• A staff member will be with you shortly\n"
            "• Please provide any additional details or screenshots\n"
            "• Do not ping staff members\n"
            "• Be patient and respectful"
        )
        await ticket_channel.send(content=welcome_msg, embed=embed, view=TicketControlsView(ticket_number))
        if template_text:
            template_embed = discord.Embed(
                title="📋 Please Fill In The Following",
                description=template_text,
                color=discord.Color.blue()
            )
            template_embed.set_footer(text="Answer each question in this channel so staff can help you faster.")
            await ticket_channel.send(embed=template_embed)

        ticket_data = load_ticket_data()
        guild_str   = str(guild.id)
        if guild_str not in ticket_data:
            ticket_data[guild_str] = {"counter": ticket_number, "tickets": {}}
        ticket_data[guild_str]["tickets"][f"ticket-{ticket_number}"] = {
            "user_id":    str(interaction.user.id),
            "category":   self.category,
            "title":      self.issue_title.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status":     "open",
            "priority":   "medium"
        }
        save_ticket_data(ticket_data)
        await interaction.response.send_message(f"✅ Ticket **#{ticket_number}** created: {ticket_channel.mention}", ephemeral=True)
        if any(word in self.category.lower() for word in ["report", "critical"]):
            if mod_role:
                await ticket_channel.send(f"{mod_role.mention} 🚨 New {self.category} ticket requires attention!")


class TicketCategoryView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


class ReportView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📨 Create Ticket", style=discord.ButtonStyle.blurple, emoji="🎫", custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="🎫 Select Ticket Category",
            description="Please select the category that best describes your issue:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=TicketCategoryView(), ephemeral=True)


# -------------------------
# Server Rules Command
# -------------------------
@bot.command(name="rules")
async def rules(ctx):
    rules_text = (
        "1️⃣ **Respect Everyone**\nBe kind and respectful. Harassment, hate speech, or bullying will not be tolerated.\n\n"
        "2️⃣ **No Spamming or Flooding**\nAvoid excessive messages, emoji spam, or mic spamming.\n\n"
        "3️⃣ **Keep It SFW**\nNo NSFW content of any kind.\n\n"
        "4️⃣ **No Self-Promotion or Advertising**\nPromoting content or servers without permission is not allowed.\n\n"
        "5️⃣ **Follow Discord's ToS**\nComply with Discord's Terms of Service and Community Guidelines.\n\n"
        "6️⃣ **No Threats or Doxxing**\nSharing personal info or threats results in an immediate ban.\n\n"
        "7️⃣ **Use Channels Properly**\nStick to each channel's topic.\n\n"
        "8️⃣ **Listen to Staff**\nModerators and admins have the final say.\n\n"
        "🚨 Breaking rules may result in warnings, mutes, kicks, or bans.\n"
    )
    embed = discord.Embed(
        title="📋 Server Rules",
        description=rules_text,
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="Please follow the rules to keep our community safe and friendly!")
    await ctx.send(embed=embed)


# -------------------------
# ADVANCED VERIFICATION SYSTEM
# -------------------------
VERIFICATION_FILE     = "verifications.json"
PENDING_VERIFICATIONS = {}

def load_verifications():
    if os.path.exists(VERIFICATION_FILE):
        with open(VERIFICATION_FILE, "r") as f:
            return json.load(f)
    return {}

def save_verifications(data):
    with open(VERIFICATION_FILE, "w") as f:
        json.dump(data, f, indent=4)

def generate_verification_code():
    return ''.join(random.choices('0123456789', k=6))

def check_account_age(member):
    now              = datetime.now(timezone.utc)
    account_age_days = (now - member.created_at).days
    flags            = []
    risk_level       = "low"
    if account_age_days < 7:
        flags.append("⚠️ Account is less than 7 days old")
        risk_level = "high"
    elif account_age_days < 30:
        flags.append("⚠️ Account is less than 30 days old")
        risk_level = "medium"
    if member.avatar is None:
        flags.append("⚠️ Using default Discord avatar")
        if risk_level == "low":
            risk_level = "medium"
    if not member.display_name or member.display_name == member.name:
        flags.append("ℹ️ No custom display name set")
    return {
        "account_age_days": account_age_days,
        "risk_level":       risk_level,
        "flags":            flags,
        "timestamp":        datetime.now(timezone.utc).isoformat()
    }


class VerifyButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔐 Verify", style=discord.ButtonStyle.success, custom_id="verify_button_main")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        config           = load_server_config(interaction.guild.id)
        verified_role_id = config.get("verified_role_id")
        if not verified_role_id:
            return await interaction.response.send_message("❌ Verification is not set up for this server.", ephemeral=True)
        verified_role = interaction.guild.get_role(verified_role_id)
        if verified_role in interaction.user.roles:
            return await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        if interaction.user.id in PENDING_VERIFICATIONS:
            time_since = datetime.now(timezone.utc) - PENDING_VERIFICATIONS[interaction.user.id]["timestamp"]
            if time_since.total_seconds() < 300:
                return await interaction.response.send_message("⏳ You already have a pending verification. Check your DMs.", ephemeral=True)
        code = generate_verification_code()
        PENDING_VERIFICATIONS[interaction.user.id] = {
            "code":       code,
            "timestamp":  datetime.now(timezone.utc),
            "attempts":   0,
            "channel_id": interaction.channel.id
        }
        try:
            dm_embed = discord.Embed(
                title="🔐 Server Verification Required",
                description=(
                    f"Welcome to **{interaction.guild.name}**!\n\n"
                    "**Step 1:** Read the server rules\n"
                    "**Step 2:** Copy your verification code below\n"
                    "**Step 3:** Type it in the verification channel\n"
                ),
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            dm_embed.add_field(name="🔑 Your Verification Code", value=f"```\n{code}\n```", inline=False)
            dm_embed.add_field(name="⚠️ Important",
                               value="• Expires in 15 minutes\n• Do not share this code\n• Type it in the verification channel",
                               inline=False)
            dm_embed.set_footer(text=f"Verification for {interaction.guild.name}")
            await interaction.user.send(embed=dm_embed)
            await interaction.response.send_message("✅ **Verification code sent to your DMs!**\n\nType the code in this channel.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⚠️ **Unable to DM you!**\n\n**Your code:** `{code}`\n\nType it in this channel. Expires in 15 minutes.",
                ephemeral=True
            )


@bot.command(name="verify")
@commands.has_permissions(administrator=True)
async def verify(ctx: commands.Context, member: discord.Member = None):
    if member is None:
        member = ctx.author
    config           = load_server_config(ctx.guild.id)
    verified_role_id = config.get("verified_role_id")
    if not verified_role_id:
        return await ctx.send("❌ Verified role not set. Use `!setup` to configure.")
    verified_role = ctx.guild.get_role(verified_role_id)
    if verified_role is None:
        return await ctx.send("❌ Verified role not found.")
    await member.add_roles(verified_role)
    verification_data = load_verifications()
    account_analysis  = check_account_age(member)
    verification_data[str(member.id)] = {
        "verified_at":      datetime.now(timezone.utc).isoformat(),
        "verified_by":      str(ctx.author.id),
        "manual":           True,
        "account_age_days": account_analysis["account_age_days"],
        "guild_id":         str(ctx.guild.id)
    }
    save_verifications(verification_data)
    await ctx.send(f"✅ {member.mention} has been manually verified!")
    try:
        embed = discord.Embed(
            title="✅ You've Been Verified!",
            description=f"An administrator has manually verified you in **{ctx.guild.name}**.\n\nYou now have full access to the server!",
            color=discord.Color.green()
        )
        await member.send(embed=embed)
    except discord.Forbidden:
        pass


@bot.command(name="sendverify")
@commands.has_permissions(administrator=True)
async def sendverify(ctx):
    embed = discord.Embed(
        title="🔐 Server Verification",
        description=(
            "Welcome! To access this server, you must verify your account.\n\n"
            "**How to verify:**\n"
            "1. Click the **Verify** button below\n"
            "2. Check your DMs for a verification code\n"
            "3. Type the code in this channel (it will be auto-deleted)\n"
            "4. Get instant access to the server!\n\n"
            "**Can't receive DMs?** The code will be shown to you privately."
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="Click the button below to start verification")
    await ctx.send(embed=embed, view=VerifyButton())


@bot.event
async def on_member_join(member):
    await asyncio.sleep(2)
    config = load_server_config(member.guild.id)

    # ── Audit log ──
    now = datetime.now(timezone.utc)
    age = (now - member.created_at).days
    audit_embed = discord.Embed(
        title="📥 Member Joined",
        color=discord.Color.green(),
        timestamp=now,
    )
    audit_embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    audit_embed.add_field(name="👤 User",        value=member.mention,                                 inline=True)
    audit_embed.add_field(name="🆔 ID",          value=str(member.id),                                 inline=True)
    audit_embed.add_field(name="📅 Account Age", value=f"{age} days old",                              inline=True)
    audit_embed.add_field(name="📅 Created",     value=f"<t:{int(member.created_at.timestamp())}:F>",  inline=False)
    audit_embed.set_thumbnail(url=member.display_avatar.url)
    audit_embed.set_footer(text=f"Member #{member.guild.member_count}")
    await send_audit(member.guild, audit_embed)

    # ── Welcome image ──
    welcome_channel_id = config.get("welcome_channel_id")
    if welcome_channel_id:
        welcome_channel = member.guild.get_channel(welcome_channel_id)
        if welcome_channel:
            try:
                img_bytes = await generate_welcome_image(member)
                welcome_embed = discord.Embed(
                    title=f"👋 Welcome to {member.guild.name}!",
                    description=(
                        f"Hey {member.mention}, we're glad you're here! 🎉\n\n"
                        f"You are member **#{member.guild.member_count}**.\n"
                        "Head to the verification channel to get started!"
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                welcome_embed.set_thumbnail(url=member.display_avatar.url)
                if img_bytes:
                    await welcome_channel.send(embed=welcome_embed,
                                               file=discord.File(img_bytes, filename="welcome.png"))
                else:
                    await welcome_channel.send(embed=welcome_embed)
            except Exception as e:
                print(f"[Welcome] Error sending welcome: {e}")

    # ── DM welcome ──
    if not config.get("verified_role_id"):
        return
    try:
        account_analysis = check_account_age(member)
        embed = discord.Embed(
            title=f"👋 Welcome to {member.guild.name}!",
            description=(
                f"Hey {member.mention}! Welcome to the server!\n\n"
                "**To get started:**\n"
                "Go to the verification channel and click the **Verify** button.\n\n"
                "See you inside! 🎉"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Account created {account_analysis['account_age_days']} days ago")
        await member.send(embed=embed)
    except discord.Forbidden:
        pass


# -------------------------
# Payment Tracking Commands
# -------------------------
@bot.command(name="pay")
@commands.has_permissions(administrator=True)
async def pay(ctx, username: str, amount: float):
    if amount <= 0:
        return await ctx.send("❌ Amount must be greater than 0.")
    payments = load_payments()
    if username not in payments:
        return await ctx.send(f"❌ {username} not found. Use `!pay_add` first.")
    if payments[username] < amount:
        await ctx.send(f"⚠️ Warning: {username} only has ${payments[username]:,.2f} owed. Proceeding anyway...")
    payments[username] -= amount
    if payments[username] <= 0:
        del payments[username]
        await ctx.send(f"✅ Paid **${amount:,.2f}** to **{username}**. Balance cleared!")
    else:
        await ctx.send(f"✅ Paid **${amount:,.2f}** to **{username}**.")
    save_payments(payments)

@bot.command(name="pay_add")
@commands.has_permissions(administrator=True)
async def pay_add(ctx, username: str, amount: float):
    if amount <= 0:
        return await ctx.send("❌ Amount must be greater than 0.")
    payments = load_payments()
    if username in payments:
        old_amount = payments[username]
        payments[username] += amount
        action_text = f"Added **${amount:,.2f}** to **{username}**'s balance (was ${old_amount:,.2f})"
    else:
        payments[username] = amount
        action_text = f"Added **{username}** to payment tracker with **${amount:,.2f}**"
    save_payments(payments)
    await ctx.send(f"✅ {action_text}. New balance: **${payments[username]:,.2f}**")

@bot.command(name="pay_remove")
@commands.has_permissions(administrator=True)
async def pay_remove(ctx, username: str):
    payments = load_payments()
    if username not in payments:
        return await ctx.send(f"❌ {username} not found.")
    removed_amount = payments[username]
    del payments[username]
    save_payments(payments)
    await ctx.send(f"✅ Removed **{username}** from payment tracker (was owed ${removed_amount:,.2f})")

@bot.command(name="pay_list")
async def pay_list(ctx):
    payments = load_payments()
    await ctx.send(embed=create_payment_embed(payments))

@bot.command(name="pay_reset")
@commands.has_permissions(administrator=True)
async def pay_reset(ctx):
    await ctx.send("⚠️ Are you sure you want to reset ALL payment data? Type `yes` to confirm.")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "yes"
    try:
        await bot.wait_for("message", check=check, timeout=30)
        save_payments({})
        await ctx.send("✅ All payment data has been reset.")
    except asyncio.TimeoutError:
        await ctx.send("❌ Reset cancelled (timed out).")


# -------------------------
# Support Ticket Command
# -------------------------
@bot.command(name="ticket")
async def ticket(ctx):
    embed = discord.Embed(
        title="📢 **Support System** 🎫",
        description="Need help? Click the button below to create a support ticket!\n\nA private support channel will be created for you where staff can assist you.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Support Ticket System")
    await ctx.send(embed=embed, view=ReportView())


# -------------------------
# Ticket Stats Command
# -------------------------
@bot.command(name="ticket_stats")
@commands.has_permissions(manage_messages=True)
async def ticket_stats(ctx):
    ticket_data = load_ticket_data()
    guild_str   = str(ctx.guild.id)
    if guild_str not in ticket_data or not ticket_data[guild_str].get("tickets"):
        return await ctx.send("📭 No ticket data found for this server.")
    tickets      = ticket_data[guild_str]["tickets"]
    total        = len(tickets)
    open_count   = sum(1 for t in tickets.values() if t.get("status") == "open")
    closed_count = sum(1 for t in tickets.values() if t.get("status") == "closed")
    close_times  = []
    for t in tickets.values():
        if t.get("created_at") and t.get("closed_at"):
            try:
                created = datetime.fromisoformat(t["created_at"])
                closed  = datetime.fromisoformat(t["closed_at"])
                close_times.append((closed - created).total_seconds() / 60)
            except Exception:
                pass
    avg_close_str = "N/A"
    if close_times:
        avg_minutes   = sum(close_times) / len(close_times)
        avg_close_str = (f"{avg_minutes:.1f} minutes" if avg_minutes < 60
                         else f"{avg_minutes / 60:.1f} hours" if avg_minutes < 1440
                         else f"{avg_minutes / 1440:.1f} days")
    ratings        = [t["rating"] for t in tickets.values() if t.get("rating")]
    avg_rating_str = "No ratings yet"
    if ratings:
        avg            = sum(ratings) / len(ratings)
        avg_rating_str = f"{'⭐' * round(avg)} ({avg:.1f}/5 from {len(ratings)} ratings)"
    categories   = defaultdict(int)
    for t in tickets.values():
        categories[t.get("category", "Unknown")] += 1
    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
    embed = discord.Embed(
        title="📊 Ticket Statistics",
        description=f"Support ticket overview for **{ctx.guild.name}**",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🎫 Total Tickets", value=str(total),        inline=True)
    embed.add_field(name="🔵 Open",          value=str(open_count),   inline=True)
    embed.add_field(name="🔒 Closed",        value=str(closed_count), inline=True)
    embed.add_field(name="⏱️ Avg Close Time", value=avg_close_str,    inline=True)
    embed.add_field(name="⭐ Avg Rating",     value=avg_rating_str,   inline=False)
    embed.add_field(name="⏰ Auto-Close",     value=f"After {TICKET_IDLE_HOURS}h opener inactivity", inline=True)
    if top_categories:
        embed.add_field(name="📋 Top Categories",
                        value="\n".join(f"• {cat}: **{count}**" for cat, count in top_categories),
                        inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


# -------------------------
# Delete Messages Command
# -------------------------
@bot.command(name="delete")
@commands.has_permissions(administrator=True)
async def delete(ctx, number: int):
    if number < 1:
        return await ctx.send("❌ You must delete at least 1 message.")
    deleted = await ctx.channel.purge(limit=number + 1)
    await ctx.send(f"🗑️ Deleted {len(deleted) - 1} message(s).", delete_after=5)


# -------------------------
# Anti-Spam Admin Commands
# -------------------------
@bot.command(name="spam_info")
@commands.has_permissions(administrator=True)
async def spam_info(ctx):
    embed = discord.Embed(title="🛡️ Anti-Spam System Info",
                          description="Current spam protection configuration",
                          color=discord.Color.blurple())
    embed.add_field(name="Settings",
                    value=(f"**Max Messages:** {anti_spam.messages_per_interval} messages\n"
                           f"**Time Window:** {anti_spam.interval_seconds} seconds\n"
                           f"**Mute Duration:** {anti_spam.timeout_seconds // 60} minutes"),
                    inline=False)
    if anti_spam.muted_users:
        muted_list = []
        for user_id, unmute_time in anti_spam.muted_users.items():
            remaining = (unmute_time - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                try:
                    user = await bot.fetch_user(user_id)
                    muted_list.append(f"• {user.mention} - {int(remaining)}s remaining")
                except Exception:
                    muted_list.append(f"• User ID: {user_id} - {int(remaining)}s remaining")
        if muted_list:
            embed.add_field(name=f"Currently Muted Users ({len(muted_list)})", value="\n".join(muted_list), inline=False)
    else:
        embed.add_field(name="Muted Users", value="None", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="unmute_user")
@commands.has_permissions(administrator=True)
async def unmute_user(ctx, member: discord.Member):
    if member.id in anti_spam.muted_users:
        del anti_spam.muted_users[member.id]
        await ctx.send(f"✅ {member.mention} has been unmuted.")
    else:
        await ctx.send(f"❌ {member.mention} is not currently muted.")

@bot.command(name="spam_config")
@commands.has_permissions(administrator=True)
async def spam_config(ctx, messages: int = None, interval: int = None, timeout: int = None):
    if messages is None or interval is None or timeout is None:
        return await ctx.send(embed=discord.Embed(
            title="⚙️ Anti-Spam Configuration",
            description="Usage: `!spam_config <max_messages> <interval_seconds> <timeout_seconds>`\n\nExample: `!spam_config 5 5 300`",
            color=discord.Color.orange()
        ))
    if messages < 1 or interval < 1 or timeout < 1:
        return await ctx.send("❌ All values must be greater than 0.")
    anti_spam.messages_per_interval = messages
    anti_spam.interval_seconds      = interval
    anti_spam.timeout_seconds       = timeout
    embed = discord.Embed(title="✅ Anti-Spam Configuration Updated", color=discord.Color.green())
    embed.add_field(name="Max Messages",  value=str(messages),                    inline=True)
    embed.add_field(name="Time Window",   value=f"{interval}s",                   inline=True)
    embed.add_field(name="Mute Duration", value=f"{timeout}s ({timeout // 60}m)", inline=True)
    await ctx.send(embed=embed)


# -------------------------
# Silent Channel Commands
# -------------------------
@bot.command(name="silent_channels")
@commands.has_permissions(administrator=True)
async def silent_channels_cmd(ctx):
    embed = discord.Embed(title="🔕 Silent Channels", description="Channels that are silent by default.", color=discord.Color.blurple())
    if SILENT_CHANNELS:
        for channel_id, channel_name in SILENT_CHANNELS.items():
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                embed.add_field(name=channel.mention, value=f"**Mode:** Silent\n**ID:** {channel_id}", inline=False)
    else:
        embed.add_field(name="No Silent Channels", value="No channels are currently in silent mode", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="enable_silent")
@commands.has_permissions(administrator=True)
async def enable_silent(ctx, channel: discord.TextChannel = None):
    if channel is None:
        channel = ctx.channel
    if channel.id in SILENT_CHANNELS:
        return await ctx.send(f"❌ {channel.mention} is already in silent mode.")
    SILENT_CHANNELS[channel.id] = channel.name
    await setup_silent_channel(channel.id, ctx.guild)
    await ctx.send(embed=discord.Embed(title="✅ Silent Mode Enabled",
                                        description=f"{channel.mention} is now silent by default.",
                                        color=discord.Color.green()))

@bot.command(name="disable_silent")
@commands.has_permissions(administrator=True)
async def disable_silent(ctx, channel: discord.TextChannel = None):
    if channel is None:
        channel = ctx.channel
    if channel.id not in SILENT_CHANNELS:
        return await ctx.send(f"❌ {channel.mention} is not in silent mode.")
    del SILENT_CHANNELS[channel.id]
    await ctx.send(embed=discord.Embed(title="✅ Silent Mode Disabled",
                                        description=f"{channel.mention} notifications are now normal.",
                                        color=discord.Color.green()))


# ─────────────────────────────────────────────────────────
# ANNOUNCEMENT COMMAND
# ─────────────────────────────────────────────────────────
COLOR_MAP = {
    "blue":   discord.Color.blue(),
    "red":    discord.Color.red(),
    "green":  discord.Color.green(),
    "gold":   discord.Color.gold(),
    "purple": discord.Color.purple(),
    "orange": discord.Color.orange(),
    "teal":   discord.Color.teal(),
    "white":  discord.Color.from_rgb(255, 255, 255),
}


class AnnouncementModal(Modal, title="📢 Create Announcement"):
    ann_title = TextInput(label="Title", placeholder="Announcement title", max_length=200, style=discord.TextStyle.short)
    ann_description = TextInput(label="Description", placeholder="Write your announcement here...",
                                style=discord.TextStyle.paragraph, max_length=4000)
    ann_color = TextInput(label="Embed Color", placeholder="blue / red / green / gold / purple / orange / teal / white",
                          default="blue", max_length=10, style=discord.TextStyle.short, required=False)
    ann_image = TextInput(label="Image URL (optional)", placeholder="https://example.com/image.png",
                          max_length=500, style=discord.TextStyle.short, required=False)

    def __init__(self, ctx: commands.Context):
        super().__init__()
        self._ctx = ctx

    async def on_submit(self, interaction: discord.Interaction):
        color_key = (self.ann_color.value or "blue").strip().lower()
        color     = COLOR_MAP.get(color_key, discord.Color.blue())
        embed     = discord.Embed(
            title=f"📢 {self.ann_title.value}",
            description=self.ann_description.value,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Sent by {self._ctx.author.display_name}",
                         icon_url=self._ctx.author.display_avatar.url)
        image_url = (self.ann_image.value or "").strip()
        if image_url:
            embed.set_image(url=image_url)
        config                  = load_server_config(self._ctx.guild.id)
        announcement_channel_id = config.get("announcement_channel_id")
        if announcement_channel_id:
            channel = self._ctx.guild.get_channel(announcement_channel_id)
            if channel:
                await channel.send(content="@everyone", embed=embed)
                await interaction.response.send_message(f"✅ Announcement sent to {channel.mention}!", ephemeral=True)
                return
        await self._ctx.channel.send(content="@everyone", embed=embed)
        await interaction.response.send_message("✅ Announcement sent! (No announcement channel set — use `!setup` to configure one.)", ephemeral=True)


class AnnouncementLaunchView(View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=60)
        self._ctx = ctx

    @discord.ui.button(label="📢 Write Announcement", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self._ctx.author.id:
            return await interaction.response.send_message("❌ This panel isn't for you.", ephemeral=True)
        await interaction.response.send_modal(AnnouncementModal(self._ctx))


@bot.command(name="announcement")
@commands.has_permissions(administrator=True)
async def announcement(ctx):
    """Create a rich announcement with title, description, color, and optional image."""
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        title="📢 Create Announcement",
        description=(
            "Click the button below to write your announcement.\n\n"
            "You'll be able to set:\n"
            "• **Title** & **Description**\n"
            "• **Embed Color** (blue, red, green, gold, purple, orange, teal, white)\n"
            "• **Image URL** (optional — shown as large image in embed)"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=AnnouncementLaunchView(ctx), delete_after=60)


# -------------------------
# Setup Command
# -------------------------
@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx):
    embed = discord.Embed(
        title="⚙️ Server Setup",
        description=(
            "Let's configure the bot for your server!\n\n"
            "**You'll need the IDs for your role and channels.**\n"
            "Enable Developer Mode in Discord settings to copy IDs.\n\n"
            "Type `skip` at any step to leave it unchanged."
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)
    config = load_server_config(ctx.guild.id)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    steps = [
        ("verified_role_id",        "🔐 **Step 1:** Paste the **Role ID** for the verified role, or type `skip`:",          "role"),
        ("announcement_channel_id", "📢 **Step 2:** Paste the **Channel ID** for announcements, or type `skip`:",           "channel"),
        ("stats_channel_id",        "📊 **Step 3:** Paste the **Channel ID** for member count stats, or type `skip`:",      "channel"),
        ("welcome_channel_id",      "👋 **Step 4:** Paste the **Channel ID** for welcome messages/images, or type `skip`:", "channel"),
        ("audit_log_channel_id",    "📋 **Step 5:** Paste the **Channel ID** for the audit log, or type `skip`:",           "channel"),
    ]
    for key, prompt, kind in steps:
        await ctx.send(prompt)
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            if msg.content.lower() != "skip":
                try:
                    obj_id = int(msg.content.strip())
                    obj    = ctx.guild.get_role(obj_id) if kind == "role" else ctx.guild.get_channel(obj_id)
                    if obj:
                        config[key] = obj_id
                        await ctx.send(f"✅ Set to **{obj.name}**")
                    else:
                        await ctx.send("⚠️ Not found. Skipping.")
                except ValueError:
                    await ctx.send("⚠️ Invalid ID. Skipping.")
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Timeout, skipping...")

    save_server_config(ctx.guild.id, config)
    final_embed = discord.Embed(title="✅ Setup Complete!", description="Your server has been configured.", color=discord.Color.green())
    items = []
    label_map = {
        "verified_role_id":        ("🔐", "Verified Role",        "role"),
        "announcement_channel_id": ("📢", "Announcement Channel", "channel"),
        "stats_channel_id":        ("📊", "Stats Channel",        "channel"),
        "welcome_channel_id":      ("👋", "Welcome Channel",      "channel"),
        "audit_log_channel_id":    ("📋", "Audit Log Channel",    "channel"),
    }
    for k, (icon, label, kind) in label_map.items():
        if config.get(k):
            obj = ctx.guild.get_role(config[k]) if kind == "role" else ctx.guild.get_channel(config[k])
            items.append(f"{icon} {label}: **{obj.name if obj else 'Unknown'}**")
    final_embed.add_field(
        name="Configured Settings" if items else "⚠️ Nothing Configured",
        value="\n".join(items) if items else "All steps were skipped.",
        inline=False
    )
    await ctx.send(embed=final_embed)


# -------------------------
# User Info Command
# -------------------------
@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    now              = datetime.now(timezone.utc)
    account_age_days = (now - member.created_at).days
    join_age_days    = (now - member.joined_at).days if member.joined_at else 0
    verification_data = load_verifications()
    user_verification = verification_data.get(str(member.id))
    if user_verification:
        verified_at   = datetime.fromisoformat(user_verification["verified_at"])
        verify_status = f"✅ Verified <t:{int(verified_at.timestamp())}:R>"
        risk_level    = user_verification.get("risk_level", "unknown")
        verify_method = user_verification.get("method", "unknown")
    else:
        verify_status = "❌ Not Verified"
        risk_level    = "N/A"
        verify_method = "N/A"
    roles     = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    roles_str = " ".join(roles) if roles else "No roles"
    if len(roles_str) > 1000:
        roles_str = f"{len(roles)} roles"

    # Warning count
    warn_data  = load_warnings()
    warn_key   = _warn_key(ctx.guild.id, member.id)
    warn_count = len(warn_data.get(warn_key, {}).get("warns", []))

    # AFK status
    afk_data   = load_afk()
    afk_status = "None"
    if str(member.id) in afk_data:
        info       = afk_data[str(member.id)]
        set_ts     = int(datetime.fromisoformat(info["set_at"]).timestamp())
        afk_status = f"💤 {info['reason']} (since <t:{set_ts}:R>)"

    embed = discord.Embed(
        title=f"👤 User Info — {member.display_name}",
        color=member.color if member.color != discord.Color.default() else discord.Color.blurple(),
        timestamp=now
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🪪 Username",            value=str(member),                                inline=True)
    embed.add_field(name="🆔 User ID",             value=str(member.id),                             inline=True)
    embed.add_field(name="🤖 Bot?",                value="Yes" if member.bot else "No",               inline=True)
    embed.add_field(name="📅 Account Created",     value=f"<t:{int(member.created_at.timestamp())}:F>\n({account_age_days} days ago)", inline=True)
    embed.add_field(name="📥 Joined Server",       value=f"<t:{int(member.joined_at.timestamp())}:F>\n({join_age_days} days ago)" if member.joined_at else "Unknown", inline=True)
    embed.add_field(name="🖼️ Avatar",              value="Custom" if member.avatar else "Default",    inline=True)
    embed.add_field(name="🔐 Verification Status", value=verify_status,                              inline=True)
    embed.add_field(name="🛡️ Risk Level",          value=risk_level.capitalize(),                    inline=True)
    embed.add_field(name="🔑 Verify Method",       value=verify_method.replace("_", " ").title(),    inline=True)
    embed.add_field(name="⚠️ Warnings",            value=f"{warn_count} warning(s)",                 inline=True)
    embed.add_field(name="💤 AFK Status",          value=afk_status,                                 inline=False)
    embed.add_field(name=f"🏷️ Roles ({len(roles)})", value=roles_str,                               inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


# -------------------------
# Server Info Command
# -------------------------
@bot.command(name="serverinfo")
async def serverinfo(ctx):
    guild  = ctx.guild
    now    = datetime.now(timezone.utc)
    age_days       = (now - guild.created_at).days
    total          = guild.member_count
    bots           = sum(1 for m in guild.members if m.bot)
    humans         = total - bots
    text_channels  = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories     = len(guild.categories)
    boost_level    = guild.premium_tier
    boost_count    = guild.premium_subscription_count or 0
    embed = discord.Embed(
        title=f"🏠 {guild.name}",
        description=guild.description or "No description set.",
        color=discord.Color.blurple(),
        timestamp=now
    )
    if guild.icon:   embed.set_thumbnail(url=guild.icon.url)
    if guild.banner: embed.set_image(url=guild.banner.url)
    embed.add_field(name="🆔 Server ID",  value=str(guild.id),                                                      inline=True)
    embed.add_field(name="👑 Owner",      value=guild.owner.mention if guild.owner else "Unknown",                   inline=True)
    embed.add_field(name="📅 Created",    value=f"<t:{int(guild.created_at.timestamp())}:F>\n({age_days} days ago)", inline=True)
    embed.add_field(name="👥 Members",    value=f"Total: **{total}**\nHumans: **{humans}**\nBots: **{bots}**",        inline=True)
    embed.add_field(name="💬 Channels",   value=f"Text: **{text_channels}**\nVoice: **{voice_channels}**\nCategories: **{categories}**", inline=True)
    embed.add_field(name="🎭 Roles",      value=str(len(guild.roles)),                                                inline=True)
    embed.add_field(name="🚀 Boost Level",value=f"Level **{boost_level}**",                                          inline=True)
    embed.add_field(name="💎 Boosts",     value=str(boost_count),                                                    inline=True)
    embed.add_field(name="😀 Emojis",     value=f"{len(guild.emojis)}/{guild.emoji_limit}",                          inline=True)
    embed.add_field(name="🔒 Verification Level", value=str(guild.verification_level).replace("_", " ").title(),     inline=True)
    embed.add_field(name="🌍 Region",     value="Automatic (Discord)",                                                inline=True)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


# -------------------------
# Remind Me Command
# -------------------------
@bot.command(name="remindme")
async def remindme(ctx, time_str: str, *, message: str):
    seconds = convert_time(time_str)
    if seconds == 0:
        return await ctx.send("❌ Invalid time format. Examples: `30s`, `10m`, `2h`, `1d`, `1h30m`")
    if seconds < 10:
        return await ctx.send("❌ Minimum reminder time is 10 seconds.")
    if seconds > 2592000:
        return await ctx.send("❌ Maximum reminder time is 30 days.")
    due_time  = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    timestamp = int(due_time.timestamp())
    reminders = load_reminders()
    reminders.append({
        "user_id":    ctx.author.id,
        "message":    message,
        "due":        due_time.isoformat(),
        "set_at":     datetime.now(timezone.utc).isoformat(),
        "channel_id": ctx.channel.id
    })
    save_reminders(reminders)
    embed = discord.Embed(
        title="⏰ Reminder Set!",
        description=f"I'll remind you via DM at <t:{timestamp}:F> (<t:{timestamp}:R>).",
        color=discord.Color.blurple()
    )
    embed.add_field(name="📝 Message", value=message, inline=False)
    embed.set_footer(text="Make sure your DMs are open so I can reach you!")
    await ctx.send(embed=embed)


# =========================================================
# GIVEAWAY SYSTEM
# =========================================================
def has_giveaway_permission(ctx: commands.Context) -> bool:
    if ctx.author.guild_permissions.administrator:
        return True
    return bool({r.name for r in ctx.author.roles} & set(GIVEAWAY_ALLOWED_ROLES))


class GiveawayModal(Modal, title="🎉 Start a Giveaway"):
    duration_input = TextInput(label="Duration", placeholder="e.g. 10s / 30m / 2h / 1d", max_length=20, style=discord.TextStyle.short)
    winners_input  = TextInput(label="Number of Winners", placeholder="e.g. 1", max_length=3, style=discord.TextStyle.short)
    prize_input    = TextInput(label="Prize", placeholder="What are you giving away?", max_length=200, style=discord.TextStyle.short)

    def __init__(self, ctx: commands.Context):
        super().__init__()
        self._ctx = ctx

    async def on_submit(self, interaction: discord.Interaction):
        seconds = convert_time(self.duration_input.value.strip())
        if seconds == 0:
            return await interaction.response.send_message("❌ Invalid duration.", ephemeral=True)
        try:
            winners = int(self.winners_input.value.strip())
            if winners < 1: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Winner count must be a positive whole number.", ephemeral=True)
        prize     = self.prize_input.value.strip()
        end_time  = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        timestamp = int(end_time.timestamp())
        await interaction.response.send_message(f"✅ Giveaway for **{prize}** started! 🎉", ephemeral=True)
        embed = discord.Embed(
            title="🎉 **GIVEAWAY** 🎉",
            description=(f"**Prize:** {prize}\n**Winners:** {winners}\n**Hosted by:** {interaction.user.mention}\n\n"
                         f"⏳ Ends: <t:{timestamp}:R> (<t:{timestamp}:F>)"),
            color=discord.Color.gold()
        )
        embed.set_footer(text="React with 🎉 to enter!")
        msg = await self._ctx.channel.send(embed=embed)
        await msg.add_reaction("🎉")
        await asyncio.sleep(seconds)
        new_msg  = await self._ctx.channel.fetch_message(msg.id)
        users    = [u async for u in new_msg.reactions[0].users() if not u.bot]
        if len(users) < winners:
            await self._ctx.channel.send("❌ Not enough entrants to determine a winner.")
            embed.description += "\n\n❌ **Giveaway ended — not enough entries.**"
            embed.color = discord.Color.red()
            embed.set_footer(text="Giveaway Ended")
            await msg.edit(embed=embed)
            return
        won_users       = random.sample(users, winners)
        winners_mention = ", ".join(u.mention for u in won_users)
        await self._ctx.channel.send(f"🎉 **CONGRATULATIONS** {winners_mention}! You won **{prize}**!")
        embed.description += f"\n\n🏆 **Winner:** {winners_mention}"
        embed.color = discord.Color.green()
        embed.set_footer(text="Giveaway Ended")
        await msg.edit(embed=embed)


class GiveawayLaunchView(View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=120)
        self._ctx = ctx

    @discord.ui.button(label="🎉 Configure Giveaway", style=discord.ButtonStyle.success)
    async def open_modal(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self._ctx.author.id:
            return await interaction.response.send_message("❌ This is not your giveaway panel.", ephemeral=True)
        await interaction.response.send_modal(GiveawayModal(self._ctx))


@bot.command(name="gstart")
async def gstart(ctx: commands.Context):
    if not has_giveaway_permission(ctx):
        return await ctx.send(
            f"❌ You need one of these roles: {', '.join(f'**{r}**' for r in GIVEAWAY_ALLOWED_ROLES)} (or Administrator).",
            delete_after=10
        )
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        title="🎉 Giveaway Setup",
        description=("Click **Configure Giveaway** to fill in the details.\n\n"
                     "• **Duration** — how long it runs\n"
                     "• **Winners** — how many people win\n"
                     "• **Prize** — what you're giving away"),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Started by {ctx.author.display_name}")
    await ctx.send(embed=embed, view=GiveawayLaunchView(ctx), delete_after=120)


# =========================================================
# Fun Commands
# =========================================================
@bot.command(name="flip")
async def flip(ctx):
    msg = await ctx.send(embed=discord.Embed(title="🪙 Flipping...", color=discord.Color.light_grey()))
    await asyncio.sleep(1)
    result = random.choice(["Heads", "Tails"])
    await msg.edit(embed=discord.Embed(title="🪙 Coin Flip", description=f"**{result.upper()}**", color=discord.Color.gold()))


# =========================================================
# Help Command
# =========================================================
@bot.command(name="help")
async def help_command(ctx):
    embeds = []

    e1 = discord.Embed(title="🤖 Bot Commands — Page 1/7", color=discord.Color.blurple())
    e1.add_field(name="**BASIC COMMANDS**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e1.add_field(name="!help",              value="Display this help message",                    inline=False)
    e1.add_field(name="!rules",             value="Display server rules",                         inline=False)
    e1.add_field(name="!ticket",            value="Create a support ticket",                      inline=False)
    e1.add_field(name="!gstart",            value="Start a giveaway via interactive menu (Mod+)", inline=False)
    e1.add_field(name="!flip",              value="Flip a coin",                                  inline=False)
    e1.add_field(name="!uptime",            value="Show how long the bot has been running",       inline=False)
    e1.add_field(name="!afk [reason]",      value="Set yourself as AFK — bot will notify pings", inline=False)
    embeds.append(e1)

    e2 = discord.Embed(title="🔴 Bot Commands — Page 2/7", color=0x53FC18)
    e2.add_field(name="**KICK LIVE ANNOUNCEMENT**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e2.add_field(name="!live",
                 value=("Opens an interactive live announcement menu.\n\n"
                        "**Step 1 —** Enter your Kick.com username\n"
                        "**Step 2 —** Select your stream category\n"
                        "**Step 3 —** Choose which Discord channel to post in\n\n"
                        "**Who can use it:** Moderator, Developer, Support, Owner, Streamer + Admins"),
                 inline=False)
    embeds.append(e2)

    e3 = discord.Embed(title="🛡️ Bot Commands — Page 3/7", color=discord.Color.orange())
    e3.add_field(name="**MODERATION (Mod/Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e3.add_field(name="!mute <@user> <time> [reason]",    value="Temp-mute a member  e.g. `!mute @user 30m Spamming`",  inline=False)
    e3.add_field(name="!unmute <@user>",                  value="Manually unmute a member",                              inline=False)
    e3.add_field(name="!tempban <@user> <time> [reason]", value="Temporarily ban a member  e.g. `!tempban @user 1d`",   inline=False)
    e3.add_field(name="!slowmode <time> [#channel]",      value="Set slowmode  e.g. `!slowmode 30s` or `!slowmode off`", inline=False)
    e3.add_field(name="**WARNING SYSTEM (Mod/Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e3.add_field(name="!warn <@user> [reason]",    value="Warn a member — auto-punishments at 3/5/7/10 warns",       inline=False)
    e3.add_field(name="!warnings [@user]",         value="View warnings (defaults to yourself)",                      inline=False)
    e3.add_field(name="!clearwarns <@user> [#]",  value="Clear all warns or a specific one  e.g. `!clearwarns @user 2`", inline=False)
    e3.add_field(name="**ANTI-SPAM (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e3.add_field(name="!spam_info",               value="Display anti-spam settings and muted users", inline=False)
    e3.add_field(name="!unmute_user <@user>",     value="Manually unmute a spam-muted user",          inline=False)
    e3.add_field(name="!spam_config <m> <i> <t>", value="Configure anti-spam thresholds",             inline=False)
    embeds.append(e3)

    e4 = discord.Embed(title="📅 Bot Commands — Page 4/7", color=discord.Color.blue())
    e4.add_field(name="**SCHEDULED ANNOUNCEMENTS (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e4.add_field(name="!schedule #channel <time> <message>",
                 value="Schedule an announcement  e.g. `!schedule #general 2h Event in 30min!`\nAdd `--everyone` at the end to ping @everyone",
                 inline=False)
    e4.add_field(name="!schedule_list",     value="View all pending scheduled announcements", inline=False)
    e4.add_field(name="!schedule_cancel #", value="Cancel a scheduled announcement by number", inline=False)
    e4.add_field(name="**AUDIT LOG (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e4.add_field(name="!setauditlog #channel",
                 value="Set the audit log channel — tracks edits, deletes, joins, leaves, bans, role changes, slowmode, warns",
                 inline=False)
    e4.add_field(name="!setauditlog", value="View the current audit log channel", inline=False)
    e4.add_field(name="**SILENT CHANNELS (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e4.add_field(name="!silent_channels",          value="View silent channels",     inline=False)
    e4.add_field(name="!enable_silent [#channel]", value="Enable silent mode",       inline=False)
    e4.add_field(name="!disable_silent [#channel]", value="Disable silent mode",     inline=False)
    embeds.append(e4)

    e5 = discord.Embed(title="💰 Bot Commands — Page 5/7", color=discord.Color.green())
    e5.add_field(name="**PAYMENT TRACKING (Admin)**",  value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e5.add_field(name="!pay <username> <amount>",      value="Record a payment",                    inline=False)
    e5.add_field(name="!pay_add <username> <amount>",  value="Add an amount owed to a user",        inline=False)
    e5.add_field(name="!pay_remove <username>",        value="Remove a user from the tracker",      inline=False)
    e5.add_field(name="!pay_list",                     value="Display all payment balances",        inline=False)
    e5.add_field(name="!pay_reset",                    value="Reset all payment data",              inline=False)
    e5.add_field(name="**VERIFICATION (Admin)**",      value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e5.add_field(name="!verify [member]",              value="Manually verify a member",            inline=False)
    e5.add_field(name="!sendverify",                   value="Send the verification button embed",  inline=False)
    e5.add_field(name="**CUSTOM COMMANDS (Admin)**",   value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e5.add_field(name="!addcmd <name> <response>",     value="Add a custom command",               inline=False)
    e5.add_field(name="!removecmd <name>",             value="Remove a custom command",             inline=False)
    e5.add_field(name="!listcmds",                     value="List all custom commands",            inline=False)
    embeds.append(e5)

    e6 = discord.Embed(title="📊 Bot Commands — Page 6/7", color=discord.Color.teal())
    e6.add_field(name="**UTILITY COMMANDS**",       value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e6.add_field(name="!userinfo [member]",         value="Show detailed member info including warns & AFK status", inline=False)
    e6.add_field(name="!serverinfo",                value="Show server stats",                                      inline=False)
    e6.add_field(name="!remindme <time> <message>", value="Set a DM reminder  e.g. `!remindme 30m Check oven`",    inline=False)
    e6.add_field(name="**TICKET TOOLS (Staff)**",   value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e6.add_field(name="!ticket_stats",              value="View ticket statistics including avg close time & ratings", inline=False)
    e6.add_field(name="**SERVER MANAGEMENT (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e6.add_field(name="!setup",      value="Interactive server config wizard (5 steps including audit log)", inline=False)
    e6.add_field(name="!delete <n>", value="Bulk delete messages",                                           inline=False)
    e6.add_field(name="!announcement", value="Create a rich announcement with color & image",                inline=False)
    embeds.append(e6)

    e7 = discord.Embed(title="📖 Bot Commands — Page 7/7", color=discord.Color.blurple())
    e7.add_field(name="**NEW FEATURES SUMMARY**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e7.add_field(name="⚠️ Warning System",
                 value="!warn with escalating auto-punishments (3→mute 1h, 5→mute 24h, 7→kick, 10→ban). Fully configurable in WARN_THRESHOLDS.", inline=False)
    e7.add_field(name="📅 Scheduled Announcements",
                 value="Schedule any message to any channel at any future time. Supports @everyone pings. Survives bot restarts.", inline=False)
    e7.add_field(name="📋 Audit Log",
                 value="Full server event logging — edits, deletes, joins, leaves, bans, role changes, nickname changes, slowmode, warns, mutes.", inline=False)
    e7.add_field(name="🐢 Slowmode",
                 value="Set slowmode on any channel with any duration. Changes are logged to the audit channel.", inline=False)
    e7.add_field(name="🔒 Ticket Auto-Close",
                 value=f"Tickets auto-close after **{TICKET_IDLE_HOURS}h** if the opener hasn't replied. Staff replies don't reset the timer — only the opener's messages do.", inline=False)
    e7.add_field(name="**SUPPORT**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e7.add_field(name="Support Server", value="[Join our support server](https://discord.gg/5FrwQAwF6N)", inline=False)
    embeds.append(e7)

    for embed in embeds:
        await ctx.send(embed=embed)


# =========================================================
# Run the bot
# =========================================================
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN not found in environment variables!")
        print("Please create a .env file with: DISCORD_BOT_TOKEN=your_token_here")
        exit(1)
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
