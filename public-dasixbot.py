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
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

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

anti_spam = AntiSpamSystem(
    messages_per_interval=5,
    interval_seconds=5,
    timeout_seconds=300
)

PAYMENTS_FILE = "payments.json"
CONFIG_FILE = "server_config.json"
REMINDERS_FILE = "reminders.json"

# Roles allowed to run giveaway commands
GIVEAWAY_ALLOWED_ROLES = ["Moderator", "Developer", "Support", "Owner"]

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


# ==========================================================
# KICK LIVE ANNOUNCEMENT SYSTEM
# ==========================================================

KICK_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://kick.com/",
    "Origin":          "https://kick.com",
    "DNT":             "1",
}

kick_live_states = {}


# ── !live COMMAND — Interactive Menu ─────────────────────

class LiveChannelSelect(Select):
    """Step 3 — pick the Discord channel to post in."""
    def __init__(self, guild: discord.Guild, kick_username: str, category: str):
        self.kick_username = kick_username
        self.category = category

        text_channels = [ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages][:25]
        options = [
            discord.SelectOption(label=f"#{ch.name}", value=str(ch.id))
            for ch in text_channels
        ]
        super().__init__(
            placeholder="Select announcement channel...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="live_channel_select"
        )

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)

        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp())

        embed = discord.Embed(
            title=f"🔴  {self.kick_username} is LIVE",
            color=0x53FC18,  # Kick green
            timestamp=now
        )
        embed.add_field(name="🎮 Category", value=self.category, inline=True)
        embed.add_field(name="📺 Platform", value="Kick.com", inline=True)
        embed.add_field(
            name="🔗 Stream Link",
            value=f"[**Watch Now → kick.com/{self.kick_username}**](https://kick.com/{self.kick_username})",
            inline=False
        )
        embed.set_footer(text=f"Went live • {now.strftime('%B %d, %Y at %I:%M %p UTC')}")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="▶  Watch Stream", url=f"https://kick.com/{self.kick_username}", style=discord.ButtonStyle.link))

        await channel.send("@everyone", embed=embed, view=view)
        await interaction.response.edit_message(
            content=f"✅ Live announcement posted in {channel.mention}!",
            embed=None,
            view=None
        )


class LiveCategorySelect(Select):
    """Step 2 — pick the stream category."""
    def __init__(self, kick_username: str):
        self.kick_username = kick_username
        options = [
            discord.SelectOption(label="🎰 Slots & Casino",     value="Slots & Casino"),
            discord.SelectOption(label="🃏 Cases & Packs",      value="Cases & Packs"),
            discord.SelectOption(label="🎮 Just Chatting",      value="Just Chatting"),
            discord.SelectOption(label="🎯 Sports Betting",     value="Sports Betting"),
            discord.SelectOption(label="🎲 Gambling",           value="Gambling"),
            discord.SelectOption(label="🕹️ Gaming",             value="Gaming"),
            discord.SelectOption(label="🎵 Music",              value="Music"),
            discord.SelectOption(label="🎙️ Podcast / IRL",      value="Podcast / IRL"),
            discord.SelectOption(label="⚽ Sports",             value="Sports"),
            discord.SelectOption(label="📦 Unboxing",           value="Unboxing"),
        ]
        super().__init__(
            placeholder="Select your stream category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="live_category_select"
        )

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
    """Step 1 — enter Kick channel name."""
    kick_username = TextInput(
        label="Your Kick.com Username",
        placeholder="e.g. NotLilKev",
        max_length=50,
        style=discord.TextStyle.short
    )

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
    """Streamer types !live — launches interactive menu to post a live announcement."""
    allowed_roles = {"Moderator", "Developer", "Support", "Owner", "Streamer"}
    author_roles = {r.name for r in ctx.author.roles}
    is_admin = ctx.author.guild_permissions.administrator

    if not is_admin and not (author_roles & allowed_roles):
        return await ctx.send(
            "❌ You don't have permission to use this command.",
            delete_after=8
        )

    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    await ctx.author.send_modal(LiveKickUsernameModal()) if False else None

    # Send modal via interaction — since !live is a prefix command we do it differently:
    # We send an ephemeral prompt with a button that opens the modal
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
        description="Click the button below to set up your live announcement.\nYou'll enter your Kick username, pick your category, and choose where to post it.",
        color=0x53FC18
    )
    embed.set_footer(text="Only visible to you")
    await ctx.send(embed=embed, view=OpenLiveModal(), delete_after=60)


# ==========================================================
# KeepAlive Task & Event Handlers
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
                    print(f"[Stats] Updated member count for {guild.name}: {guild.member_count}")
                except Exception as e:
                    print(f"[Stats] Error updating channel in {guild.name}: {e}")

@tasks.loop(seconds=30)
async def reminder_loop():
    reminders = load_reminders()
    now = datetime.now(timezone.utc)
    remaining = []
    for reminder in reminders:
        due_time = datetime.fromisoformat(reminder["due"])
        if now >= due_time:
            try:
                user = await bot.fetch_user(reminder["user_id"])
                embed = discord.Embed(
                    title="⏰ Reminder!",
                    description=reminder["message"],
                    color=discord.Color.blurple(),
                    timestamp=now
                )
                embed.set_footer(text="This reminder was set by you")
                await user.send(embed=embed)
            except Exception as e:
                print(f"[Reminders] Could not send reminder to {reminder['user_id']}: {e}")
        else:
            remaining.append(reminder)
    save_reminders(remaining)


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
    print("[Bot] All background tasks started")


# -------------------------
# ANTI-SPAM & SILENT CHANNEL MESSAGE HANDLER
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
        print(f"[AntiSpam] {message.author} ({message.author.id}) detected as spammer in #{message.channel.name}")
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
                            account_analysis = check_account_age(message.author)
                            verification_data[str(message.author.id)] = {
                                "verified_at": datetime.now(timezone.utc).isoformat(),
                                "account_age_days": account_analysis["account_age_days"],
                                "risk_level": account_analysis["risk_level"],
                                "guild_id": str(message.guild.id),
                                "method": "channel_code"
                            }
                            save_verifications(verification_data)
                            del PENDING_VERIFICATIONS[message.author.id]
                            success_msg = await message.channel.send(
                                f"✅ **{message.author.mention} Verification successful!** You now have access to the server."
                            )
                            await asyncio.sleep(5)
                            try:
                                await success_msg.delete()
                            except:
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
                    except:
                        pass

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
    messages = [message async for message in channel.history(limit=None, oldest_first=True)]
    message_html = ""
    for msg in messages:
        timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
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
        self.guild_name = guild_name

    async def _record_rating(self, interaction: discord.Interaction, stars: int, label: str):
        ticket_data = load_ticket_data()
        for guild_str, guild_data in ticket_data.items():
            ticket_key = f"ticket-{self.ticket_number}"
            if ticket_key in guild_data.get("tickets", {}):
                guild_data["tickets"][ticket_key]["rating"] = stars
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

    @discord.ui.button(label="⭐", style=discord.ButtonStyle.secondary, custom_id="rate_1")
    async def rate_1(self, interaction: discord.Interaction, button: Button):
        await self._record_rating(interaction, 1, "⭐ (1/5)")

    @discord.ui.button(label="⭐⭐", style=discord.ButtonStyle.secondary, custom_id="rate_2")
    async def rate_2(self, interaction: discord.Interaction, button: Button):
        await self._record_rating(interaction, 2, "⭐⭐ (2/5)")

    @discord.ui.button(label="⭐⭐⭐", style=discord.ButtonStyle.secondary, custom_id="rate_3")
    async def rate_3(self, interaction: discord.Interaction, button: Button):
        await self._record_rating(interaction, 3, "⭐⭐⭐ (3/5)")

    @discord.ui.button(label="⭐⭐⭐⭐", style=discord.ButtonStyle.secondary, custom_id="rate_4")
    async def rate_4(self, interaction: discord.Interaction, button: Button):
        await self._record_rating(interaction, 4, "⭐⭐⭐⭐ (4/5)")

    @discord.ui.button(label="⭐⭐⭐⭐⭐", style=discord.ButtonStyle.success, custom_id="rate_5")
    async def rate_5(self, interaction: discord.Interaction, button: Button):
        await self._record_rating(interaction, 5, "⭐⭐⭐⭐⭐ (5/5)")


class TicketCategorySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="💰 General Support",    description="General questions and support",        emoji="💰"),
            discord.SelectOption(label="⚙️ Technical Support",  description="Bot or server technical issues",       emoji="⚙️"),
            discord.SelectOption(label="👤 Account Issues",     description="Verification or account problems",     emoji="👤"),
            discord.SelectOption(label="📢 Report User/Issue",  description="Report a user or problem",             emoji="📢"),
            discord.SelectOption(label="💡 Suggestion",         description="Suggest improvements",                 emoji="💡"),
            discord.SelectOption(label="❓ General Question",   description="General inquiry",                      emoji="❓"),
        ]
        super().__init__(
            placeholder="Select a ticket category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_category = self.values[0]
        await interaction.response.send_modal(ReportModal(selected_category))


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
        embed.add_field(name="⏰ Claimed At", value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:R>", inline=True)
        for i, field in enumerate(embed.fields):
            if field.name == "📝 Status":
                embed.set_field_at(i, name="📝 Status", value="🟡 Claimed", inline=True)
        embed.set_footer(text=f"Ticket #{self.ticket_number} | Status: CLAIMED")
        button.disabled = True
        button.label = "✅ Claimed"
        button.style = discord.ButtonStyle.success
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message(f"✅ {interaction.user.mention} has claimed this ticket!", ephemeral=False)
        ticket_data = load_ticket_data()
        guild_str = str(interaction.guild.id)
        ticket_str = f"ticket-{self.ticket_number}"
        if guild_str in ticket_data and ticket_str in ticket_data[guild_str].get("tickets", {}):
            ticket_data[guild_str]["tickets"][ticket_str]["claimed_by"] = str(interaction.user.id)
            ticket_data[guild_str]["tickets"][ticket_str]["claimed_at"] = datetime.now(timezone.utc).isoformat()
            save_ticket_data(ticket_data)

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_callback(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_messages:
            if str(interaction.user.id) not in interaction.channel.topic:
                return await interaction.response.send_message("❌ Only staff or the ticket owner can close this.", ephemeral=True)
        await interaction.response.send_message("🔒 Generating transcript and closing ticket...", ephemeral=True)
        html_transcript = await generate_transcript(interaction.channel)
        ticket_number = interaction.channel.name.split("-")[-1]
        user_id = interaction.channel.topic.split("ID: ")[-1] if interaction.channel.topic else "Unknown"
        ticket_data = load_ticket_data()
        guild_str = str(interaction.guild.id)
        ticket_str = f"ticket-{ticket_number}"
        closed_at_iso = datetime.now(timezone.utc).isoformat()
        if guild_str in ticket_data and ticket_str in ticket_data[guild_str].get("tickets", {}):
            tkt = ticket_data[guild_str]["tickets"][ticket_str]
            tkt["closed_by"] = str(interaction.user.id)
            tkt["closed_at"] = closed_at_iso
            tkt["status"] = "closed"
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
        try:
            member = interaction.guild.get_member(int(user_id))
            if member:
                html_transcript.seek(0)
                dm_embed = discord.Embed(
                    title="Ticket Closed",
                    description=f"Your ticket **#{ticket_number}** in **{interaction.guild.name}** has been closed.\n\nThank you for contacting support!",
                    color=discord.Color.red()
                )
                await member.send(
                    embed=dm_embed,
                    file=discord.File(html_transcript, filename=f"ticket-{ticket_number}-transcript.html")
                )
                rating_embed = discord.Embed(
                    title="⭐ How was your support experience?",
                    description=(
                        f"Please rate your experience for ticket **#{ticket_number}** in **{interaction.guild.name}**.\n\n"
                        "Your feedback helps us improve our support quality!"
                    ),
                    color=discord.Color.gold()
                )
                rating_view = TicketRatingView(ticket_number, interaction.guild.name)
                await member.send(embed=rating_embed, view=rating_view)
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
        view = PrioritySelectView(interaction.message, self.ticket_number)
        await interaction.response.send_message("Select new priority level:", view=view, ephemeral=True)


class AddUserModal(Modal):
    def __init__(self, channel):
        super().__init__(title="Add User to Ticket")
        self.channel = channel
        self.user_input = TextInput(label="User ID or @mention", placeholder="Enter user ID or mention them", style=discord.TextStyle.short)
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.user_input.value.strip().replace("<@", "").replace(">", "").replace("!", "")
        try:
            user_id = int(user_input)
            member = interaction.guild.get_member(user_id)
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
        self.message = message
        self.ticket_number = ticket_number
        options = [
            discord.SelectOption(label="🟢 Low Priority",      value="low",      emoji="🟢"),
            discord.SelectOption(label="🟡 Medium Priority",   value="medium",   emoji="🟡"),
            discord.SelectOption(label="🟠 High Priority",     value="high",     emoji="🟠"),
            discord.SelectOption(label="🔴 Critical Priority", value="critical", emoji="🔴"),
        ]
        select = Select(placeholder="Choose priority level", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        priority = interaction.data["values"][0]
        embed = self.message.embeds[0]
        priority_display = {
            "low":      "🟢 Low",
            "medium":   "🟡 Medium",
            "high":     "🟠 High",
            "critical": "🔴 Critical"
        }
        for i, field in enumerate(embed.fields):
            if field.name == "⚡ Priority":
                embed.set_field_at(i, name="⚡ Priority", value=priority_display[priority], inline=True)
        await self.message.edit(embed=embed)
        await interaction.response.send_message(f"✅ Priority updated to **{priority_display[priority]}**", ephemeral=True)
        await interaction.channel.send(f"⚠️ Ticket priority changed to **{priority_display[priority]}** by {interaction.user.mention}")


class ReportModal(Modal):
    def __init__(self, category):
        super().__init__(title=f"🎫 Create Ticket - {category}")
        self.category = category
        self.issue_title = TextInput(label="Title", placeholder="Brief summary of your issue", max_length=100, style=discord.TextStyle.short)
        self.issue_details = TextInput(
            label="Details", style=discord.TextStyle.paragraph,
            placeholder="Please describe your issue in detail. Include any relevant information, screenshots, or links.",
            min_length=20, max_length=1000
        )
        self.add_item(self.issue_title)
        self.add_item(self.issue_details)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        existing_tickets = [ch for ch in guild.text_channels if f"ticket-{interaction.user.name.lower()}" in ch.name.lower()]
        for ticket in existing_tickets:
            if ticket.topic and str(interaction.user.id) in ticket.topic:
                await interaction.response.send_message(f"⚠️ You already have an open ticket: {ticket.mention}", ephemeral=True)
                return
        ticket_number = get_next_ticket_number(guild.id)
        category = discord.utils.get(guild.categories, name="📬 Support Tickets")
        if not category:
            category = await guild.create_category("📬 Support Tickets")
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
            category=category,
            topic=f"Ticket #{ticket_number} | User: {interaction.user.name} | ID: {interaction.user.id}",
            overwrites=overwrites
        )
        embed = discord.Embed(
            title=f"🎫 {self.issue_title.value}",
            description=f"**Category:** {self.category}\n**Opened By:** {interaction.user.mention} ({interaction.user.id})",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="⚡ Priority",       value="🟡 Medium",        inline=True)
        embed.add_field(name="📝 Status",         value="🔵 Open",          inline=True)
        embed.add_field(name="🎫 Ticket Number",  value=f"#{ticket_number}", inline=True)
        embed.add_field(name="📋 Issue Details",  value=f"```\n{self.issue_details.value[:500]}\n```", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Ticket #{ticket_number} | Created")
        view = TicketControlsView(ticket_number)
        welcome_msg = (
            f"{interaction.user.mention} Welcome to your support ticket!\n\n"
            "**What to expect:**\n"
            "• A staff member will be with you shortly\n"
            "• Please provide any additional details or screenshots\n"
            "• Do not ping staff members\n"
            "• Be patient and respectful\n\n"
            "**Need urgent help?** @ mention a moderator if this is critical."
        )
        await ticket_channel.send(content=welcome_msg, embed=embed, view=view)
        ticket_data = load_ticket_data()
        guild_str = str(guild.id)
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
        view = TicketCategoryView()
        embed = discord.Embed(
            title="🎫 Select Ticket Category",
            description="Please select the category that best describes your issue:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# -------------------------
# Server Rules Command
# -------------------------
@bot.command(name="rules")
async def rules(ctx):
    rules_text = (
        "1️⃣ **Respect Everyone**\n"
        "Be kind and respectful to all members. Harassment, hate speech, discrimination, or bullying will not be tolerated.\n\n"
        "2️⃣ **No Spamming or Flooding**\n"
        "Avoid excessive messages, emoji spam, or mic spamming in voice channels.\n\n"
        "3️⃣ **Keep It Safe for Work (SFW)**\n"
        "No NSFW content, including images, links, or discussions.\n\n"
        "4️⃣ **No Self-Promotion or Advertising**\n"
        "Promoting your own content, servers, or services without permission is not allowed.\n\n"
        "5️⃣ **Follow Discord's Terms of Service**\n"
        "Ensure you comply with Discord's ToS and Community Guidelines.\n\n"
        "6️⃣ **No Threats or Doxxing**\n"
        "Sharing personal information, threats, or doxxing will result in an immediate ban.\n\n"
        "7️⃣ **Use Channels Properly**\n"
        "Stick to the topic of each channel. Off-topic discussions should go to general chat.\n\n"
        "8️⃣ **Listen to Staff**\n"
        "Moderators and admins have the final say. If you have concerns, message them privately.\n\n"
        "🚨 Breaking any of these rules may result in warnings, mutes, kicks, or bans.\n"
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
VERIFICATION_FILE = "verifications.json"
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
    now = datetime.now(timezone.utc)
    account_age_days = (now - member.created_at).days
    flags = []
    risk_level = "low"
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
        "risk_level": risk_level,
        "flags": flags,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


class VerifyButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔐 Verify", style=discord.ButtonStyle.success, custom_id="verify_button_main")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        config = load_server_config(interaction.guild.id)
        verified_role_id = config.get("verified_role_id")
        if not verified_role_id:
            return await interaction.response.send_message("❌ Verification is not set up for this server.", ephemeral=True)
        verified_role = interaction.guild.get_role(verified_role_id)
        if verified_role in interaction.user.roles:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
            return
        if interaction.user.id in PENDING_VERIFICATIONS:
            time_since = datetime.now(timezone.utc) - PENDING_VERIFICATIONS[interaction.user.id]["timestamp"]
            if time_since.total_seconds() < 300:
                await interaction.response.send_message("⏳ You already have a pending verification. Check your DMs.", ephemeral=True)
                return
        code = generate_verification_code()
        PENDING_VERIFICATIONS[interaction.user.id] = {
            "code": code,
            "timestamp": datetime.now(timezone.utc),
            "attempts": 0,
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
            dm_embed.add_field(name="⚠️ Important", value="• Expires in 15 minutes\n• Do not share this code\n• Type it in the verification channel", inline=False)
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
    config = load_server_config(ctx.guild.id)
    verified_role_id = config.get("verified_role_id")
    if not verified_role_id:
        return await ctx.send("❌ Verified role not set. Use `!setup` to configure.")
    verified_role = ctx.guild.get_role(verified_role_id)
    if verified_role is None:
        return await ctx.send("❌ Verified role not found.")
    await member.add_roles(verified_role)
    verification_data = load_verifications()
    account_analysis = check_account_age(member)
    verification_data[str(member.id)] = {
        "verified_at":     datetime.now(timezone.utc).isoformat(),
        "verified_by":     str(ctx.author.id),
        "manual":          True,
        "account_age_days": account_analysis["account_age_days"],
        "guild_id":        str(ctx.guild.id)
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
    view = VerifyButton()
    await ctx.send(embed=embed, view=view)


@bot.event
async def on_member_join(member):
    await asyncio.sleep(2)
    config = load_server_config(member.guild.id)
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
    embed = create_payment_embed(payments)
    await ctx.send(embed=embed)


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
    view = ReportView()
    await ctx.send(embed=embed, view=view)


# -------------------------
# Ticket Stats Command
# -------------------------
@bot.command(name="ticket_stats")
@commands.has_permissions(manage_messages=True)
async def ticket_stats(ctx):
    ticket_data = load_ticket_data()
    guild_str = str(ctx.guild.id)
    if guild_str not in ticket_data or not ticket_data[guild_str].get("tickets"):
        return await ctx.send("📭 No ticket data found for this server.")
    tickets = ticket_data[guild_str]["tickets"]
    total        = len(tickets)
    open_count   = sum(1 for t in tickets.values() if t.get("status") == "open")
    closed_count = sum(1 for t in tickets.values() if t.get("status") == "closed")
    close_times = []
    for t in tickets.values():
        if t.get("created_at") and t.get("closed_at"):
            try:
                created = datetime.fromisoformat(t["created_at"])
                closed  = datetime.fromisoformat(t["closed_at"])
                diff = (closed - created).total_seconds() / 60
                close_times.append(diff)
            except:
                pass
    avg_close_str = "N/A"
    if close_times:
        avg_minutes = sum(close_times) / len(close_times)
        if avg_minutes < 60:
            avg_close_str = f"{avg_minutes:.1f} minutes"
        elif avg_minutes < 1440:
            avg_close_str = f"{avg_minutes / 60:.1f} hours"
        else:
            avg_close_str = f"{avg_minutes / 1440:.1f} days"
    ratings = [t["rating"] for t in tickets.values() if t.get("rating")]
    avg_rating_str = "No ratings yet"
    if ratings:
        avg = sum(ratings) / len(ratings)
        avg_rating_str = f"{'⭐' * round(avg)} ({avg:.1f}/5 from {len(ratings)} ratings)"
    categories = defaultdict(int)
    for t in tickets.values():
        cat = t.get("category", "Unknown")
        categories[cat] += 1
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
    if top_categories:
        cat_text = "\n".join([f"• {cat}: **{count}**" for cat, count in top_categories])
        embed.add_field(name="📋 Top Categories", value=cat_text, inline=False)
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
    embed = discord.Embed(title="🛡️ Anti-Spam System Info", description="Current spam protection configuration", color=discord.Color.blurple())
    embed.add_field(
        name="Settings",
        value=(
            f"**Max Messages:** {anti_spam.messages_per_interval} messages\n"
            f"**Time Window:** {anti_spam.interval_seconds} seconds\n"
            f"**Mute Duration:** {anti_spam.timeout_seconds // 60} minutes"
        ),
        inline=False
    )
    if anti_spam.muted_users:
        muted_list = []
        for user_id, unmute_time in anti_spam.muted_users.items():
            remaining = (unmute_time - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                try:
                    user = await bot.fetch_user(user_id)
                    muted_list.append(f"• {user.mention} - {int(remaining)}s remaining")
                except:
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
        embed = discord.Embed(
            title="⚙️ Anti-Spam Configuration",
            description="Usage: `!spam_config <max_messages> <interval_seconds> <timeout_seconds>`\n\nExample: `!spam_config 5 5 300`",
            color=discord.Color.orange()
        )
        return await ctx.send(embed=embed)
    if messages < 1 or interval < 1 or timeout < 1:
        return await ctx.send("❌ All values must be greater than 0.")
    anti_spam.messages_per_interval = messages
    anti_spam.interval_seconds      = interval
    anti_spam.timeout_seconds       = timeout
    embed = discord.Embed(title="✅ Anti-Spam Configuration Updated", color=discord.Color.green())
    embed.add_field(name="Max Messages",  value=str(messages),                   inline=True)
    embed.add_field(name="Time Window",   value=f"{interval}s",                  inline=True)
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
    embed = discord.Embed(title="✅ Silent Mode Enabled", description=f"{channel.mention} is now silent by default.", color=discord.Color.green())
    await ctx.send(embed=embed)


@bot.command(name="disable_silent")
@commands.has_permissions(administrator=True)
async def disable_silent(ctx, channel: discord.TextChannel = None):
    if channel is None:
        channel = ctx.channel
    if channel.id not in SILENT_CHANNELS:
        return await ctx.send(f"❌ {channel.mention} is not in silent mode.")
    del SILENT_CHANNELS[channel.id]
    embed = discord.Embed(title="✅ Silent Mode Disabled", description=f"{channel.mention} notifications are now normal.", color=discord.Color.green())
    await ctx.send(embed=embed)


# -------------------------
# Announcement Command
# -------------------------
@bot.command(name="announcement")
@commands.has_permissions(administrator=True)
async def announcement(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("📝 What should the **title** of the announcement be?")
    try:
        title_msg = await bot.wait_for("message", check=check, timeout=60)
        title = title_msg.content
    except:
        return await ctx.send("❌ You took too long. Announcement cancelled.")

    await ctx.send("💬 Great! Now, what should the **description** be?")
    try:
        desc_msg = await bot.wait_for("message", check=check, timeout=180)
        description = desc_msg.content
    except:
        return await ctx.send("❌ You took too long. Announcement cancelled.")

    embed = discord.Embed(
        title=f"📢 {title}",
        description=description,
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Sent by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    config = load_server_config(ctx.guild.id)
    announcement_channel_id = config.get("announcement_channel_id")
    if announcement_channel_id:
        channel = ctx.guild.get_channel(announcement_channel_id)
        if channel:
            await channel.send(content="@everyone", embed=embed)
            await ctx.send(f"✅ Announcement sent to {channel.mention}")
        else:
            await ctx.send("❌ Announcement channel not found. Use `!setup` to configure.")
    else:
        await ctx.send(embed=embed)
        await ctx.send("ℹ️ Use `!setup` to set an announcement channel.")


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

    # Step 1: Verified role
    await ctx.send("🔐 **Step 1:** Paste the **Role ID** for the verified role, or type `skip`:")
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.content.lower() != "skip":
            try:
                role_id = int(msg.content.strip())
                role = ctx.guild.get_role(role_id)
                if role:
                    config["verified_role_id"] = role_id
                    await ctx.send(f"✅ Verified role set to **{role.name}**")
                else:
                    await ctx.send("⚠️ No role found with that ID. Skipping.")
            except ValueError:
                await ctx.send("⚠️ Invalid ID. Skipping.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Timeout, skipping...")

    # Step 2: Announcement channel
    await ctx.send("📢 **Step 2:** Paste the **Channel ID** for announcements, or type `skip`:")
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.content.lower() != "skip":
            try:
                channel_id = int(msg.content.strip())
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    config["announcement_channel_id"] = channel_id
                    await ctx.send(f"✅ Announcement channel set to **{channel.name}**")
                else:
                    await ctx.send("⚠️ No channel found with that ID. Skipping.")
            except ValueError:
                await ctx.send("⚠️ Invalid ID. Skipping.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Timeout, skipping...")

    # Step 3: Stats channel
    await ctx.send("📊 **Step 3:** Paste the **Channel ID** for member count stats, or type `skip`:")
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.content.lower() != "skip":
            try:
                channel_id = int(msg.content.strip())
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    config["stats_channel_id"] = channel_id
                    await ctx.send(f"✅ Stats channel set to **{channel.name}**")
                else:
                    await ctx.send("⚠️ No channel found with that ID. Skipping.")
            except ValueError:
                await ctx.send("⚠️ Invalid ID. Skipping.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Timeout, skipping...")

    save_server_config(ctx.guild.id, config)

    final_embed = discord.Embed(title="✅ Setup Complete!", description="Your server has been configured.", color=discord.Color.green())
    configured_items = []
    if config.get("verified_role_id"):
        role = ctx.guild.get_role(config["verified_role_id"])
        configured_items.append(f"🔐 Verified Role: **{role.name if role else 'Unknown'}**")
    if config.get("announcement_channel_id"):
        ch = ctx.guild.get_channel(config["announcement_channel_id"])
        configured_items.append(f"📢 Announcement Channel: **{ch.name if ch else 'Unknown'}**")
    if config.get("stats_channel_id"):
        ch = ctx.guild.get_channel(config["stats_channel_id"])
        configured_items.append(f"📊 Stats Channel: **{ch.name if ch else 'Unknown'}**")
    if configured_items:
        final_embed.add_field(name="Configured Settings", value="\n".join(configured_items), inline=False)
    else:
        final_embed.add_field(name="⚠️ Nothing Configured", value="All steps were skipped.", inline=False)
    await ctx.send(embed=final_embed)


# -------------------------
# User Info Command
# -------------------------
@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    now = datetime.now(timezone.utc)
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
    roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    roles_str = " ".join(roles) if roles else "No roles"
    if len(roles_str) > 1000:
        roles_str = f"{len(roles)} roles"
    embed = discord.Embed(
        title=f"👤 User Info — {member.display_name}",
        color=member.color if member.color != discord.Color.default() else discord.Color.blurple(),
        timestamp=now
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🪪 Username",        value=str(member),                              inline=True)
    embed.add_field(name="🆔 User ID",         value=str(member.id),                           inline=True)
    embed.add_field(name="🤖 Bot?",            value="Yes" if member.bot else "No",             inline=True)
    embed.add_field(name="📅 Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>\n({account_age_days} days ago)", inline=True)
    embed.add_field(name="📥 Joined Server",   value=f"<t:{int(member.joined_at.timestamp())}:F>\n({join_age_days} days ago)" if member.joined_at else "Unknown", inline=True)
    embed.add_field(name="🖼️ Avatar",          value="Custom" if member.avatar else "Default",  inline=True)
    embed.add_field(name="🔐 Verification Status", value=verify_status,                        inline=True)
    embed.add_field(name="🛡️ Risk Level",      value=risk_level.capitalize(),                  inline=True)
    embed.add_field(name="🔑 Verify Method",   value=verify_method.replace("_", " ").title(),  inline=True)
    embed.add_field(name=f"🏷️ Roles ({len(roles)})", value=roles_str,                         inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)


# -------------------------
# Server Info Command
# -------------------------
@bot.command(name="serverinfo")
async def serverinfo(ctx):
    guild = ctx.guild
    now = datetime.now(timezone.utc)
    age_days = (now - guild.created_at).days
    total  = guild.member_count
    bots   = sum(1 for m in guild.members if m.bot)
    humans = total - bots
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
    embed.add_field(name="🆔 Server ID",  value=str(guild.id),                                              inline=True)
    embed.add_field(name="👑 Owner",      value=guild.owner.mention if guild.owner else "Unknown",          inline=True)
    embed.add_field(name="📅 Created",    value=f"<t:{int(guild.created_at.timestamp())}:F>\n({age_days} days ago)", inline=True)
    embed.add_field(name="👥 Members",    value=f"Total: **{total}**\nHumans: **{humans}**\nBots: **{bots}**", inline=True)
    embed.add_field(name="💬 Channels",   value=f"Text: **{text_channels}**\nVoice: **{voice_channels}**\nCategories: **{categories}**", inline=True)
    embed.add_field(name="🎭 Roles",      value=str(len(guild.roles)),                                      inline=True)
    embed.add_field(name="🚀 Boost Level",value=f"Level **{boost_level}**",                                inline=True)
    embed.add_field(name="💎 Boosts",     value=str(boost_count),                                          inline=True)
    embed.add_field(name="😀 Emojis",     value=f"{len(guild.emojis)}/{guild.emoji_limit}",                inline=True)
    embed.add_field(name="🔒 Verification Level", value=str(guild.verification_level).replace("_", " ").title(), inline=True)
    embed.add_field(name="🌍 Region",     value="Automatic (Discord)",                                      inline=True)
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
    author_role_names = {r.name for r in ctx.author.roles}
    return bool(author_role_names & set(GIVEAWAY_ALLOWED_ROLES))


class GiveawayModal(Modal, title="🎉 Start a Giveaway"):
    duration_input = TextInput(
        label="Duration",
        placeholder="e.g. 10s  /  30m  /  2h  /  1d",
        max_length=20,
        style=discord.TextStyle.short
    )
    winners_input = TextInput(
        label="Number of Winners",
        placeholder="e.g. 1",
        max_length=3,
        style=discord.TextStyle.short
    )
    prize_input = TextInput(
        label="Prize",
        placeholder="What are you giving away?",
        max_length=200,
        style=discord.TextStyle.short
    )

    def __init__(self, ctx: commands.Context):
        super().__init__()
        self._ctx = ctx

    async def on_submit(self, interaction: discord.Interaction):
        seconds = convert_time(self.duration_input.value.strip())
        if seconds == 0:
            return await interaction.response.send_message(
                "❌ Invalid duration. Examples: `10s`, `30m`, `2h`, `1d`", ephemeral=True
            )
        try:
            winners = int(self.winners_input.value.strip())
            if winners < 1:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Winner count must be a positive whole number.", ephemeral=True
            )
        prize = self.prize_input.value.strip()
        await interaction.response.send_message(
            f"✅ Giveaway for **{prize}** started! Good luck everyone 🎉",
            ephemeral=True
        )
        end_time  = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        timestamp = int(end_time.timestamp())
        embed = discord.Embed(
            title="🎉 **GIVEAWAY** 🎉",
            description=(
                f"**Prize:** {prize}\n"
                f"**Winners:** {winners}\n"
                f"**Hosted by:** {interaction.user.mention}\n\n"
                f"⏳ Ends: <t:{timestamp}:R> (<t:{timestamp}:F>)"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="React with 🎉 to enter!")
        channel = self._ctx.channel
        msg = await channel.send(embed=embed)
        await msg.add_reaction("🎉")
        await asyncio.sleep(seconds)
        new_msg = await channel.fetch_message(msg.id)
        users: list[discord.User] = []
        async for user in new_msg.reactions[0].users():
            if not user.bot:
                users.append(user)
        if len(users) < winners:
            await channel.send("❌ Not enough entrants to determine a winner.")
            embed.description += "\n\n❌ **Giveaway ended — not enough entries.**"
            embed.color = discord.Color.red()
            embed.set_footer(text="Giveaway Ended")
            await msg.edit(embed=embed)
            return
        won_users       = random.sample(users, winners)
        winners_mention = ", ".join(u.mention for u in won_users)
        await channel.send(f"🎉 **CONGRATULATIONS** {winners_mention}! You won **{prize}**!")
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
    """Start a giveaway — available to Moderator, Developer, Support, Owner, or Admins."""
    if not has_giveaway_permission(ctx):
        return await ctx.send(
            f"❌ You need one of these roles to start a giveaway: "
            f"{', '.join(f'**{r}**' for r in GIVEAWAY_ALLOWED_ROLES)} (or Administrator).",
            delete_after=10
        )
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    embed = discord.Embed(
        title="🎉 Giveaway Setup",
        description=(
            "Click **Configure Giveaway** to fill in the details.\n\n"
            "You'll be asked for:\n"
            "• **Duration** — how long the giveaway runs\n"
            "• **Winners** — how many people win\n"
            "• **Prize** — what you're giving away"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Started by {ctx.author.display_name}")
    view = GiveawayLaunchView(ctx)
    await ctx.send(embed=embed, view=view, delete_after=120)


# =========================================================
# Fun Commands
# =========================================================
@bot.command(name="flip")
async def flip(ctx):
    choices = ["Heads", "Tails"]
    result  = random.choice(choices)
    msg = await ctx.send(embed=discord.Embed(title="🪙 Flipping...", color=discord.Color.light_grey()))
    await asyncio.sleep(1)
    embed = discord.Embed(title="🪙 Coin Flip", description=f"**{result.upper()}**", color=discord.Color.gold())
    await msg.edit(embed=embed)


# =========================================================
# Help Command
# =========================================================
@bot.command(name="help")
async def help_command(ctx):
    embeds = []

    # Page 1 — Basic
    e1 = discord.Embed(title="🤖 Bot Commands — Page 1/5", color=discord.Color.blurple())
    e1.add_field(name="**BASIC COMMANDS**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e1.add_field(name="!help",      value="Display this help message",                           inline=False)
    e1.add_field(name="!rules",     value="Display server rules",                                inline=False)
    e1.add_field(name="!ticket",    value="Create a support ticket",                             inline=False)
    e1.add_field(name="!gstart",    value="Start a giveaway via interactive menu (Moderator+)",  inline=False)
    e1.add_field(name="!flip",      value="Flip a coin",                                         inline=False)
    embeds.append(e1)

    # Page 2 — Live Announcement
    e2 = discord.Embed(title="🔴 Bot Commands — Page 2/5", color=0x53FC18)
    e2.add_field(name="**KICK LIVE ANNOUNCEMENT**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e2.add_field(
        name="!live",
        value=(
            "Opens an interactive live announcement menu.\n\n"
            "**Step 1 —** Enter your Kick.com username\n"
            "**Step 2 —** Select your stream category from the dropdown\n"
            "**Step 3 —** Choose which Discord channel to post the notification in\n\n"
            "The bot will post a clean @everyone live notification with your stream link.\n\n"
            "**Who can use it:** Moderator, Developer, Support, Owner, Streamer roles + Admins"
        ),
        inline=False
    )
    embeds.append(e2)

    # Page 3 — Anti-Spam & Silent
    e3 = discord.Embed(title="🛡️ Bot Commands — Page 3/5", color=discord.Color.orange())
    e3.add_field(name="**ANTI-SPAM COMMANDS (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e3.add_field(name="!spam_info",                               value="Display anti-spam settings and muted users",  inline=False)
    e3.add_field(name="!unmute_user <member>",                    value="Manually unmute a user",                      inline=False)
    e3.add_field(name="!spam_config <msgs> <interval> <timeout>", value="Configure anti-spam thresholds",              inline=False)
    e3.add_field(name="**SILENT CHANNEL COMMANDS (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e3.add_field(name="!silent_channels",         value="View all channels with silent mode enabled", inline=False)
    e3.add_field(name="!enable_silent [channel]",  value="Enable silent mode for a channel",          inline=False)
    e3.add_field(name="!disable_silent [channel]", value="Disable silent mode for a channel",         inline=False)
    embeds.append(e3)

    # Page 4 — Payments & Verification
    e4 = discord.Embed(title="💰 Bot Commands — Page 4/5", color=discord.Color.green())
    e4.add_field(name="**PAYMENT TRACKING (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e4.add_field(name="!pay <username> <amount>",     value="Record a payment (subtracts from balance)", inline=False)
    e4.add_field(name="!pay_add <username> <amount>", value="Add an amount owed to a user",              inline=False)
    e4.add_field(name="!pay_remove <username>",       value="Remove a user from the tracker",            inline=False)
    e4.add_field(name="!pay_list",                    value="Display all current payment balances",      inline=False)
    e4.add_field(name="!pay_reset",                   value="Reset all payment data (requires confirmation)", inline=False)
    e4.add_field(name="**VERIFICATION (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e4.add_field(name="!verify [member]", value="Manually verify a member",          inline=False)
    e4.add_field(name="!sendverify",      value="Send the verification button embed", inline=False)
    embeds.append(e4)

    # Page 5 — Utility & Management
    e5 = discord.Embed(title="📊 Bot Commands — Page 5/5", color=discord.Color.teal())
    e5.add_field(name="**UTILITY COMMANDS**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e5.add_field(name="!userinfo [member]",
                 value="Show detailed info about a member — join date, roles, account age, verification status", inline=False)
    e5.add_field(name="!serverinfo",
                 value="Show server stats — member count, channels, boosts, creation date and more", inline=False)
    e5.add_field(name="!remindme <time> <message>",
                 value="Set a personal reminder delivered via DM\nExamples: `!remindme 30m Check oven` / `!remindme 1h30m Meeting`", inline=False)
    e5.add_field(name="**TICKET TOOLS (Staff)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e5.add_field(name="!ticket_stats",
                 value="View ticket statistics — total, open/closed count, avg close time, avg rating and top categories", inline=False)
    e5.add_field(name="**SERVER MANAGEMENT (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e5.add_field(name="!setup",           value="Interactive server configuration wizard", inline=False)
    e5.add_field(name="!delete <number>", value="Bulk delete messages from a channel",    inline=False)
    e5.add_field(name="!announcement",    value="Create and send a server announcement",  inline=False)
    e5.add_field(name="**SUPPORT**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    e5.add_field(name="Support Server", value="[Join our support server](https://discord.gg/PMDtKbUfEA)", inline=False)
    embeds.append(e5)

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
