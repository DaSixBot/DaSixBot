import os
import socket
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
from collections import defaultdict

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
        """Check if user is currently muted"""
        if user_id in self.muted_users:
            if datetime.now(timezone.utc) < self.muted_users[user_id]:
                return True
            else:
                del self.muted_users[user_id]
        return False
    
    def add_message(self, user_id):
        """Record a message from user and return if they're spamming"""
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
        """Mute a user for the timeout duration"""
        unmute_time = datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds)
        self.muted_users[user_id] = unmute_time
    
    def get_mute_remaining(self, user_id):
        """Get remaining mute time in seconds"""
        if user_id in self.muted_users:
            remaining = (self.muted_users[user_id] - datetime.now(timezone.utc)).total_seconds()
            return max(0, remaining)
        return 0


# -------------------------
# CHANNEL SILENT MODE SYSTEM
# -------------------------
# Configurable per server - admins can add channels
SILENT_CHANNELS = {}

async def setup_silent_channel(channel_id, guild):
    """Configure a channel to be silent by default"""
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


# ---------------------------------
# DNS OVERRIDE WORKAROUND FOR DISCORD
# ---------------------------------
DISCORD_IP_MAP = {
    "discord.com": "162.159.137.232",
    "gateway.discord.gg": "162.159.130.233",
}

_original_getaddrinfo = socket.getaddrinfo

def custom_getaddrinfo(host, *args, **kwargs):
    for domain, ip in DISCORD_IP_MAP.items():
        if domain in host:
            print(f"[DNS Override] Resolving {host} as {ip}")
            return _original_getaddrinfo(ip, *args, **kwargs)
    return _original_getaddrinfo(host, *args, **kwargs)

socket.getaddrinfo = custom_getaddrinfo

# -------------------------
# Bot Initialization & Configs
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# Initialize Anti-Spam System
anti_spam = AntiSpamSystem(
    messages_per_interval=5,
    interval_seconds=5,
    timeout_seconds=300
)

# Global variables and constants
PAYMENTS_FILE = "payments.json"
CONFIG_FILE = "server_config.json"

# Server-specific configuration
def load_server_config(guild_id):
    """Load server-specific configuration"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            all_configs = json.load(f)
            return all_configs.get(str(guild_id), {})
    return {}

def save_server_config(guild_id, config):
    """Save server-specific configuration"""
    all_configs = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            all_configs = json.load(f)
    
    all_configs[str(guild_id)] = config
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(all_configs, f, indent=4)

def load_payments():
    """Load payment data from JSON file"""
    if os.path.exists(PAYMENTS_FILE):
        with open(PAYMENTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_payments(payments):
    """Save payment data to JSON file"""
    with open(PAYMENTS_FILE, "w") as f:
        json.dump(payments, f, indent=4)

def create_payment_embed(payments):
    """Create an embed showing all payment balances"""
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
            embed.add_field(
                name=f"👤 {username}",
                value=f"**${amount:,.2f}**",
                inline=True
            )
    
    embed.set_footer(text="Last updated")
    return embed

# ---------------------------------
# KeepAlive Task & Event Handlers
# ---------------------------------

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
    """Updates member count stats for all servers"""
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

@bot.event
async def on_disconnect():
    print("[WARNING] Bot disconnected from Discord...")

@bot.event
async def on_resumed():
    print("[INFO] Bot reconnected to Discord.")

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="!help | Multi-Server Bot"))
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} servers")
    
    # Start tasks
    keep_alive.start()
    update_stats.start()
    
    print("[Bot] All background tasks started")

# -------------------------
# ANTI-SPAM & SILENT CHANNEL MESSAGE HANDLER
# -------------------------
@bot.event
async def on_message(message):
    """Handle messages for spam detection and silent channels"""
    
    # Ignore bot messages
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # Skip DMs
    if not message.guild:
        await bot.process_commands(message)
        return
    
    user_id = message.author.id
    
    # Check if user is spamming
    if anti_spam.is_user_muted(user_id):
        try:
            await message.delete()
            remaining = anti_spam.get_mute_remaining(user_id)
            warning = await message.channel.send(
                f"⏱️ {message.author.mention}, you're currently muted for spam. "
                f"You can send messages again in {int(remaining)} seconds.",
                delete_after=10
            )
        except discord.Forbidden:
            print(f"[AntiSpam] Could not delete message from {message.author}")
        return
    
    # Check for spam
    if anti_spam.add_message(user_id):
        anti_spam.mute_user(user_id)
        
        print(f"[AntiSpam] {message.author} ({message.author.id}) detected as spammer in #{message.channel.name}")
        
        try:
            await message.delete()
        except discord.Forbidden:
            print(f"[AntiSpam] Could not delete spam message from {message.author}")
        
        try:
            embed = discord.Embed(
                title="⚠️ Spam Detected",
                description=(
                    f"You've been temporarily muted for spamming.\n\n"
                    f"**Reason:** Sending too many messages too quickly\n"
                    f"**Duration:** 5 minutes\n\n"
                    f"Please slow down and follow server rules."
                ),
                color=discord.Color.red()
            )
            await message.author.send(embed=embed)
        except discord.Forbidden:
            print(f"[AntiSpam] Could not DM {message.author}")
        
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
    
    # Handle silent channels
    if message.channel.id in SILENT_CHANNELS:
        is_admin = message.author.guild_permissions.administrator
        
        # If admin sends a message with @everyone, let it through
        if is_admin and message.guild.default_role in message.mentions:
            await bot.process_commands(message)
            return
        
        # If admin sends ANY message, add @everyone to trigger notifications
        if is_admin and message.guild.default_role not in message.mentions:
            try:
                await message.edit(content=f"@everyone {message.content}")
            except discord.Forbidden:
                print(f"[SilentMode] Could not edit admin message in {message.channel.name}")
            await bot.process_commands(message)
            return
        
        # Non-admin users: remove any @everyone/@here attempts
        if message.guild.default_role in message.mentions or "@here" in message.content:
            try:
                content = message.content
                content = content.replace("@everyone", "")
                content = content.replace("@here", "")
                await message.edit(content=content)
                
                try:
                    dm_embed = discord.Embed(
                        title="🔕 Notification Silenced",
                        description=f"Your message in {message.channel.mention} cannot ping @everyone.\n\nOnly admins can use @everyone in this channel to trigger notifications.",
                        color=discord.Color.orange()
                    )
                    await message.author.send(embed=dm_embed)
                except discord.Forbidden:
                    pass
            except discord.Forbidden:
                print(f"[SilentMode] Could not edit message in {message.channel.name}")
            
            await bot.process_commands(message)
            return
    
    # Handle verification codes (if in pending verifications)
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
    
    # Process normal commands
    await bot.process_commands(message)

        
# -------------------------
# Advanced Support Ticket System
# -------------------------

TICKET_DATA_FILE = "tickets.json"

def load_ticket_data():
    """Load ticket data from JSON"""
    if os.path.exists(TICKET_DATA_FILE):
        with open(TICKET_DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_ticket_data(data):
    """Save ticket data to JSON"""
    with open(TICKET_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_next_ticket_number(guild_id):
    """Get next ticket number for the guild"""
    ticket_data = load_ticket_data()
    guild_str = str(guild_id)
    
    if guild_str not in ticket_data:
        ticket_data[guild_str] = {"counter": 0, "tickets": {}}
    
    ticket_data[guild_str]["counter"] += 1
    save_ticket_data(ticket_data)
    return ticket_data[guild_str]["counter"]

async def generate_transcript(channel):
    """Generates a detailed HTML transcript of the channel history"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Ticket Transcript - {channel_name}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #36393f;
                color: #dcddde;
                margin: 20px;
            }}
            .header {{
                background: #202225;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
            }}
            .message {{
                background: #40444b;
                padding: 15px;
                margin: 10px 0;
                border-radius: 8px;
                border-left: 4px solid #7289da;
            }}
            .author {{
                color: #7289da;
                font-weight: bold;
            }}
            .timestamp {{
                color: #72767d;
                font-size: 12px;
            }}
            .content {{
                margin-top: 8px;
                line-height: 1.5;
            }}
            .attachment {{
                color: #00b0f4;
                text-decoration: none;
                display: block;
                margin-top: 5px;
            }}
            .system {{
                background: #2f3136;
                border-left: 4px solid #faa61a;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Ticket Transcript: {channel_name}</h1>
            <p>Generated at: {timestamp}</p>
            <p>Total Messages: {message_count}</p>
        </div>
        <div class="messages">
        {messages}
        </div>
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

class TicketCategorySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="💰 General Support", description="General questions and support", emoji="💰"),
            discord.SelectOption(label="⚙️ Technical Support", description="Bot or server technical issues", emoji="⚙️"),
            discord.SelectOption(label="👤 Account Issues", description="Verification or account problems", emoji="👤"),
            discord.SelectOption(label="📢 Report User/Issue", description="Report a user or problem", emoji="📢"),
            discord.SelectOption(label="💡 Suggestion", description="Suggest improvements", emoji="💡"),
            discord.SelectOption(label="❓ General Question", description="General inquiry", emoji="❓"),
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
        
        close_embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"**Ticket #{ticket_number}** has been closed.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        close_embed.add_field(name="Closed By", value=interaction.user.mention, inline=True)
        close_embed.add_field(name="Channel", value=interaction.channel.name, inline=True)
        
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
        except:
            pass

        ticket_data = load_ticket_data()
        guild_str = str(interaction.guild.id)
        ticket_str = f"ticket-{ticket_number}"
        if guild_str in ticket_data and ticket_str in ticket_data[guild_str].get("tickets", {}):
            ticket_data[guild_str]["tickets"][ticket_str]["closed_by"] = str(interaction.user.id)
            ticket_data[guild_str]["tickets"][ticket_str]["closed_at"] = datetime.now(timezone.utc).isoformat()
            ticket_data[guild_str]["tickets"][ticket_str]["status"] = "closed"
            save_ticket_data(ticket_data)

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
        
        self.user_input = TextInput(
            label="User ID or @mention",
            placeholder="Enter user ID or mention them",
            style=discord.TextStyle.short
        )
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
            discord.SelectOption(label="🟢 Low Priority", value="low", emoji="🟢"),
            discord.SelectOption(label="🟡 Medium Priority", value="medium", emoji="🟡"),
            discord.SelectOption(label="🟠 High Priority", value="high", emoji="🟠"),
            discord.SelectOption(label="🔴 Critical Priority", value="critical", emoji="🔴"),
        ]
        
        select = Select(placeholder="Choose priority level", options=options)
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        priority = interaction.data["values"][0]
        
        embed = self.message.embeds[0]
        
        priority_display = {
            "low": "🟢 Low",
            "medium": "🟡 Medium",
            "high": "🟠 High",
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
        
        self.issue_title = TextInput(
            label="Title",
            placeholder="Brief summary of your issue",
            max_length=100,
            style=discord.TextStyle.short
        )
        
        self.issue_details = TextInput(
            label="Details",
            style=discord.TextStyle.paragraph,
            placeholder="Please describe your issue in detail. Include any relevant information, screenshots, or links.",
            min_length=20,
            max_length=1000
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
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_messages=True)
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
        
        embed.add_field(name="⚡ Priority", value="🟡 Medium", inline=True)
        embed.add_field(name="📝 Status", value="🔵 Open", inline=True)
        embed.add_field(name="🎫 Ticket Number", value=f"#{ticket_number}", inline=True)
        embed.add_field(name="📋 Issue Details", value=f"```\n{self.issue_details.value[:500]}\n```", inline=False)
        
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Ticket #{ticket_number} | Created")

        view = TicketControlsView(ticket_number)
        
        welcome_msg = f"""
{interaction.user.mention} Welcome to your support ticket!

**What to expect:**
• A staff member will be with you shortly
• Please provide any additional details or screenshots
• Do not ping staff members
• Be patient and respectful

**Need urgent help?** @ mention a moderator if this is critical.
        """

        await ticket_channel.send(content=welcome_msg, embed=embed, view=view)
        
        ticket_data = load_ticket_data()
        guild_str = str(guild.id)
        if guild_str not in ticket_data:
            ticket_data[guild_str] = {"counter": ticket_number, "tickets": {}}
        
        ticket_data[guild_str]["tickets"][f"ticket-{ticket_number}"] = {
            "user_id": str(interaction.user.id),
            "category": self.category,
            "title": self.issue_title.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "open",
            "priority": "medium"
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
    """Display server rules"""
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
        "🚨 Breaking any of these rules may result in warnings, mutes, kicks, or bans. Let's keep the server a fun and friendly place!\n\n"
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
    """Load verification data"""
    if os.path.exists(VERIFICATION_FILE):
        with open(VERIFICATION_FILE, "r") as f:
            return json.load(f)
    return {}

def save_verifications(data):
    """Save verification data"""
    with open(VERIFICATION_FILE, "w") as f:
        json.dump(data, f, indent=4)

def generate_verification_code():
    """Generate a random 6-digit verification code"""
    return ''.join(random.choices('0123456789', k=6))

def check_account_age(member):
    """Check if account meets age requirements"""
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
            return await interaction.response.send_message("❌ Verification is not set up for this server. Please contact an administrator.", ephemeral=True)
        
        verified_role = interaction.guild.get_role(verified_role_id)
        if verified_role in interaction.user.roles:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
            return
        
        if interaction.user.id in PENDING_VERIFICATIONS:
            time_since = datetime.now(timezone.utc) - PENDING_VERIFICATIONS[interaction.user.id]["timestamp"]
            if time_since.total_seconds() < 300:
                await interaction.response.send_message(
                    "⏳ You already have a pending verification. Please check your DMs for the code or type it in this channel.",
                    ephemeral=True
                )
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
                    "To verify your account and gain access to the server, please follow these steps:\n\n"
                    "**Step 1:** Read the server rules in the verification channel\n"
                    "**Step 2:** Copy your verification code below\n"
                    "**Step 3:** Type your code in the verification channel\n"
                    "**Step 4:** Your message will be automatically deleted for security\n\n"
                ),
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            dm_embed.add_field(
                name="🔑 Your Verification Code",
                value=f"```\n{code}\n```",
                inline=False
            )
            
            dm_embed.add_field(
                name="⚠️ Important",
                value="• This code expires in 15 minutes\n• Do not share this code with anyone\n• Type it in the verification channel, it will be deleted automatically\n• If you didn't request this, ignore this message",
                inline=False
            )
            
            dm_embed.set_footer(text=f"Verification for {interaction.guild.name}")
            
            await interaction.user.send(embed=dm_embed)
            await interaction.response.send_message(
                "✅ **Verification code sent to your DMs!**\n\nType the code in this channel and it will be automatically deleted for security.",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⚠️ **Unable to send you a DM!**\n\n"
                f"**Your verification code is:** `{code}`\n\n"
                f"**Next steps:**\n"
                f"1. Copy the code above\n"
                f"2. Type it in this channel\n"
                f"3. Your message will be automatically deleted\n\n"
                f"**Note:** This code expires in 15 minutes.",
                ephemeral=True
            )

@bot.command(name="verify")
@commands.has_permissions(administrator=True)
async def verify(ctx: commands.Context, member: discord.Member = None):
    """Manually verify a member"""
    if member is None:
        member = ctx.author
    
    config = load_server_config(ctx.guild.id)
    verified_role_id = config.get("verified_role_id")
    
    if not verified_role_id:
        return await ctx.send("❌ Verified role not set. Use `!setup` to configure.")
    
    verified_role = ctx.guild.get_role(verified_role_id)
    if verified_role is None:
        await ctx.send("❌ Verified role not found. Please check the role ID.")
        return
    
    await member.add_roles(verified_role)
    
    verification_data = load_verifications()
    account_analysis = check_account_age(member)
    
    verification_data[str(member.id)] = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "verified_by": str(ctx.author.id),
        "manual": True,
        "account_age_days": account_analysis["account_age_days"],
        "guild_id": str(ctx.guild.id)
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
    """Send the verification embed with button"""
    embed = discord.Embed(
        title="🔐 Server Verification",
        description=(
            "Welcome! To access this server, you must verify your account.\n\n"
            "**Why verify?**\n"
            "• Prevents spam and raids\n"
            "• Protects against bots\n"
            "• Keeps the community safe\n\n"
            "**How to verify:**\n"
            "1. Click the **Verify** button below\n"
            "2. Check your DMs for a verification code\n"
            "3. Type the code in this channel (it will be auto-deleted)\n"
            "4. Get instant access to the server!\n\n"
            "**Can't receive DMs?**\n"
            "No problem! The code will be shown to you privately when you click verify.\n\n"
            "**Need help?**\n"
            "Contact a moderator for assistance."
        ),
        color=discord.Color.blue()
    )
    
    embed.set_footer(text="Click the button below to start verification")
    
    view = VerifyButton()
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_member_join(member):
    """Send verification instructions when a new member joins"""
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
                "Go to the verification channel and click the **Verify** button.\n"
                "You'll receive a code to complete verification.\n\n"
                "See you inside! 🎉"
            ),
            color=discord.Color.blue()
        )
        
        embed.set_footer(text=f"Account created {account_analysis['account_age_days']} days ago")
        
        await member.send(embed=embed)
        
    except discord.Forbidden:
        print(f"Could not DM {member.display_name} - DMs are closed")
            
# -------------------------
# Payment Tracking Commands
# -------------------------
async def update_payment_embed(ctx, channel_id=None):
    """Update or create the persistent payment tracking embed"""
    payments = load_payments()
    embed = create_payment_embed(payments)
    
    channel = ctx.channel
    if channel_id:
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = ctx.channel
    
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Error updating payment embed: {e}")

@bot.command(name="pay")
@commands.has_permissions(administrator=True)
async def pay(ctx, username: str, amount: float):
    """Record a payment. This subtracts from their balance."""
    if amount <= 0:
        return await ctx.send("❌ Amount must be greater than 0.")
    
    payments = load_payments()
    
    if username not in payments:
        return await ctx.send(f"❌ {username} not found in payment system. Use `!pay_add` first.")
    
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
    """Add/update payment owed."""
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
    """Remove someone from the payment tracker completely."""
    payments = load_payments()
    
    if username not in payments:
        return await ctx.send(f"❌ {username} not found in payment system.")
    
    removed_amount = payments[username]
    del payments[username]
    save_payments(payments)
    
    await ctx.send(f"✅ Removed **{username}** from payment tracker (was owed ${removed_amount:,.2f})")

@bot.command(name="pay_list")
async def pay_list(ctx):
    """Display current payment balances (anyone can view)"""
    payments = load_payments()
    embed = create_payment_embed(payments)
    await ctx.send(embed=embed)

@bot.command(name="pay_reset")
@commands.has_permissions(administrator=True)
async def pay_reset(ctx):
    """Reset all payment data (requires confirmation)"""
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
    """Send ticket creation embed"""
    embed = discord.Embed(
        title="📢 **Support System** 🎫",
        description=(
            "Need help? Click the button below to create a support ticket!\n\n"
            "A private support channel will be created for you where staff can assist you."
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="Support Ticket System")
    view = ReportView()
    await ctx.send(embed=embed, view=view)

# -------------------------
# Delete Messages Command
# -------------------------
@bot.command(name="delete")
@commands.has_permissions(administrator=True)
async def delete(ctx, number: int):
    """Delete a specified number of messages"""
    if number < 1:
        await ctx.send("❌ You must delete at least 1 message.")
        return

    deleted = await ctx.channel.purge(limit=number + 1)
    await ctx.send(f"🗑️ Deleted {len(deleted) - 1} message(s).", delete_after=5)

# -------------------------
# Anti-Spam Admin Commands
# -------------------------
@bot.command(name="spam_info")
@commands.has_permissions(administrator=True)
async def spam_info(ctx):
    """Display current anti-spam settings and muted users"""
    embed = discord.Embed(
        title="🛡️ Anti-Spam System Info",
        description="Current spam protection configuration",
        color=discord.Color.blurple()
    )
    
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
            embed.add_field(
                name=f"Currently Muted Users ({len(muted_list)})",
                value="\n".join(muted_list),
                inline=False
            )
    else:
        embed.add_field(name="Muted Users", value="None", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="unmute_user")
@commands.has_permissions(administrator=True)
async def unmute_user(ctx, member: discord.Member):
    """Manually unmute a user"""
    if member.id in anti_spam.muted_users:
        del anti_spam.muted_users[member.id]
        await ctx.send(f"✅ {member.mention} has been unmuted.")
    else:
        await ctx.send(f"❌ {member.mention} is not currently muted.")

@bot.command(name="spam_config")
@commands.has_permissions(administrator=True)
async def spam_config(ctx, messages: int = None, interval: int = None, timeout: int = None):
    """Configure anti-spam settings"""
    if messages is None or interval is None or timeout is None:
        embed = discord.Embed(
            title="⚙️ Anti-Spam Configuration",
            description=(
                "Usage: `!spam_config <max_messages> <interval_seconds> <timeout_seconds>`\n\n"
                "Example: `!spam_config 5 5 300`\n"
                "This means: 5 messages per 5 seconds = mute for 5 minutes"
            ),
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    if messages < 1 or interval < 1 or timeout < 1:
        return await ctx.send("❌ All values must be greater than 0.")
    
    anti_spam.messages_per_interval = messages
    anti_spam.interval_seconds = interval
    anti_spam.timeout_seconds = timeout
    
    embed = discord.Embed(
        title="✅ Anti-Spam Configuration Updated",
        color=discord.Color.green()
    )
    embed.add_field(name="Max Messages", value=str(messages), inline=True)
    embed.add_field(name="Time Window", value=f"{interval}s", inline=True)
    embed.add_field(name="Mute Duration", value=f"{timeout}s ({timeout // 60}m)", inline=True)
    
    await ctx.send(embed=embed)

# -------------------------
# Silent Channel Commands
# -------------------------
@bot.command(name="silent_channels")
@commands.has_permissions(administrator=True)
async def silent_channels(ctx):
    """View channels with silent mode enabled"""
    embed = discord.Embed(
        title="🔕 Silent Channels",
        description="Channels that are silent by default. Only admin messages trigger @everyone notifications.",
        color=discord.Color.blurple()
    )
    
    if SILENT_CHANNELS:
        for channel_id, channel_name in SILENT_CHANNELS.items():
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                embed.add_field(
                    name=channel.mention,
                    value=f"**Mode:** Silent by default\n**ID:** {channel_id}",
                    inline=False
                )
    else:
        embed.add_field(name="No Silent Channels", value="No channels are currently in silent mode", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="enable_silent")
@commands.has_permissions(administrator=True)
async def enable_silent(ctx, channel: discord.TextChannel = None):
    """Enable silent mode for a channel"""
    if channel is None:
        channel = ctx.channel
    
    if channel.id in SILENT_CHANNELS:
        return await ctx.send(f"❌ {channel.mention} is already in silent mode.")
    
    SILENT_CHANNELS[channel.id] = channel.name
    await setup_silent_channel(channel.id, ctx.guild)
    
    embed = discord.Embed(
        title="✅ Silent Mode Enabled",
        description=f"{channel.mention} is now silent by default.\n\nOnly admin messages with @everyone will trigger notifications.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="disable_silent")
@commands.has_permissions(administrator=True)
async def disable_silent(ctx, channel: discord.TextChannel = None):
    """Disable silent mode for a channel"""
    if channel is None:
        channel = ctx.channel
    
    if channel.id not in SILENT_CHANNELS:
        return await ctx.send(f"❌ {channel.mention} is not in silent mode.")
    
    del SILENT_CHANNELS[channel.id]
    
    embed = discord.Embed(
        title="✅ Silent Mode Disabled",
        description=f"{channel.mention} notifications are now normal.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# -------------------------
# Announcement Command
# -------------------------
@bot.command(name="announcement")
@commands.has_permissions(administrator=True)
async def announcement(ctx):
    """Create an announcement"""
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
    """Interactive server setup"""
    embed = discord.Embed(
        title="⚙️ Server Setup",
        description="Let's configure the bot for your server!",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)
    
    config = load_server_config(ctx.guild.id)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    # Verified Role
    await ctx.send("🔐 **Step 1:** Mention the verified role or type `skip` to skip:")
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.content.lower() != "skip":
            if msg.role_mentions:
                config["verified_role_id"] = msg.role_mentions[0].id
                await ctx.send(f"✅ Verified role set to {msg.role_mentions[0].mention}")
            else:
                await ctx.send("⚠️ No role mentioned, skipping.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Timeout, skipping...")
    
    # Announcement Channel
    await ctx.send("📢 **Step 2:** Mention the announcement channel or type `skip`:")
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.content.lower() != "skip":
            if msg.channel_mentions:
                config["announcement_channel_id"] = msg.channel_mentions[0].id
                await ctx.send(f"✅ Announcement channel set to {msg.channel_mentions[0].mention}")
            else:
                await ctx.send("⚠️ No channel mentioned, skipping.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Timeout, skipping...")
    
    # Stats Channel
    await ctx.send("📊 **Step 3:** Mention a voice channel for member count stats or type `skip`:")
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.content.lower() != "skip":
            # Try to parse channel ID from message
            try:
                channel_id = int(msg.content.strip().replace("<#", "").replace(">", ""))
                channel = ctx.guild.get_channel(channel_id)
                if channel and isinstance(channel, discord.VoiceChannel):
                    config["stats_channel_id"] = channel_id
                    await ctx.send(f"✅ Stats channel set to {channel.name}")
                else:
                    await ctx.send("⚠️ Invalid voice channel, skipping.")
            except:
                await ctx.send("⚠️ Invalid channel ID, skipping.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Timeout, skipping...")
    
    save_server_config(ctx.guild.id, config)
    
    final_embed = discord.Embed(
        title="✅ Setup Complete!",
        description="Your server has been configured.",
        color=discord.Color.green()
    )
    
    if config:
        final_embed.add_field(name="Configuration", value=json.dumps(config, indent=2), inline=False)
    
    await ctx.send(embed=final_embed)

# -------------------------
# Admin Help Command
# -------------------------
@bot.command(name="help")
async def help_command(ctx):
    """Display bot commands"""
    embeds = []
    
    # Page 1: Basic Commands
    embed1 = discord.Embed(title="🤖 Bot Commands - Page 1/4", color=discord.Color.blurple())
    embed1.add_field(name="**BASIC COMMANDS**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed1.add_field(name="!help", value="Display this help message", inline=False)
    embed1.add_field(name="!rules", value="Display server rules", inline=False)
    embed1.add_field(name="!ticket", value="Create a support ticket", inline=False)
    embed1.add_field(name="!gstart <time> <winners> <prize>", value="Start a giveaway (Admin)", inline=False)
    embed1.add_field(name="!flip", value="Flip a coin", inline=False)
    embeds.append(embed1)
    
    # Page 2: Anti-Spam & Silent Channels
    embed2 = discord.Embed(title="🛡️ Bot Commands - Page 2/4", color=discord.Color.orange())
    embed2.add_field(name="**ANTI-SPAM COMMANDS (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed2.add_field(name="!spam_info", value="Display anti-spam settings", inline=False)
    embed2.add_field(name="!unmute_user <member>", value="Manually unmute a user", inline=False)
    embed2.add_field(name="!spam_config <msgs> <interval> <timeout>", value="Configure anti-spam", inline=False)
    
    embed2.add_field(name="**SILENT CHANNEL COMMANDS (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed2.add_field(name="!silent_channels", value="View silent channels", inline=False)
    embed2.add_field(name="!enable_silent [channel]", value="Enable silent mode", inline=False)
    embed2.add_field(name="!disable_silent [channel]", value="Disable silent mode", inline=False)
    embeds.append(embed2)
    
    # Page 3: Payment & Verification
    embed3 = discord.Embed(title="💰 Bot Commands - Page 3/4", color=discord.Color.green())
    embed3.add_field(name="**PAYMENT TRACKING (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed3.add_field(name="!pay <username> <amount>", value="Record a payment", inline=False)
    embed3.add_field(name="!pay_add <username> <amount>", value="Add amount owed", inline=False)
    embed3.add_field(name="!pay_remove <username>", value="Remove from tracker", inline=False)
    embed3.add_field(name="!pay_list", value="Display payment balances", inline=False)
    
    embed3.add_field(name="**VERIFICATION (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed3.add_field(name="!verify [member]", value="Manually verify a member", inline=False)
    embed3.add_field(name="!sendverify", value="Send verification button", inline=False)
    embeds.append(embed3)
    
    # Page 4: Management
    embed4 = discord.Embed(title="⚙️ Bot Commands - Page 4/4", color=discord.Color.red())
    embed4.add_field(name="**SERVER MANAGEMENT (Admin)**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed4.add_field(name="!setup", value="Interactive server configuration", inline=False)
    embed4.add_field(name="!delete <number>", value="Delete messages", inline=False)
    embed4.add_field(name="!announcement", value="Create an announcement", inline=False)
    
    embed4.add_field(name="**SUPPORT**", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
    embed4.add_field(name="Support Server", value="[Join our support server](https://discord.gg/PMDtKbUfEA)", inline=False)
    embed4.add_field(name="Invite Bot", value="[Invite this bot to your server](https://discord.com/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot)", inline=False)
    embeds.append(embed4)
    
    for embed in embeds:
        await ctx.send(embed=embed)

# -------------------------
# 🎁 GIVEAWAY SYSTEM
# -------------------------
def convert_time(time_str):
    """Converts 1h, 30m, 10s into seconds"""
    time_regex = re.compile(r"(\d+)([smhd])")
    matches = time_regex.findall(time_str)
    total_seconds = 0
    for value, unit in matches:
        if unit == "s": total_seconds += int(value)
        elif unit == "m": total_seconds += int(value) * 60
        elif unit == "h": total_seconds += int(value) * 3600
        elif unit == "d": total_seconds += int(value) * 86400
    return total_seconds

@bot.command(name="gstart")
@commands.has_permissions(administrator=True)
async def gstart(ctx, duration: str, winners: int, *, prize: str):
    """Start a giveaway"""
    await ctx.message.delete()

    seconds = convert_time(duration)
    if seconds == 0:
        await ctx.send("❌ Invalid time format. Use 10s, 30m, 1h, 1d.", delete_after=10)
        return

    end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    timestamp = int(end_time.timestamp())

    embed = discord.Embed(
        title="🎉 **GIVEAWAY** 🎉",
        description=(
            f"**Prize:** {prize}\n"
            f"**Winners:** {winners}\n"
            f"**Hosted by:** {ctx.author.mention}\n\n"
            f"⏳ Ends: <t:{timestamp}:R> (<t:{timestamp}:F>)"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="React with 🎉 to enter!")

    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")

    await asyncio.sleep(seconds)

    new_msg = await ctx.channel.fetch_message(msg.id)
    
    users = []
    async for user in new_msg.reactions[0].users():
        if not user.bot:
            users.append(user)

    if len(users) < winners:
        await ctx.send("❌ Not enough entrants to determine a winner.")
        return

    won_users = random.sample(users, winners)
    winners_mention = ", ".join([user.mention for user in won_users])

    await ctx.send(f"🎉 **CONGRATULATIONS** {winners_mention}! You won **{prize}**!")
    
    embed.description += f"\n\n🏆 **Winner:** {winners_mention}"
    embed.color = discord.Color.green()
    embed.set_footer(text="Giveaway Ended")
    await msg.edit(embed=embed)

# -------------------------
# 🪙 FUN COMMANDS
# -------------------------
@bot.command(name="flip")
async def flip(ctx):
    """Simple 50/50 Coin Flip"""
    choices = ["Heads", "Tails"]
    result = random.choice(choices)
    
    embed = discord.Embed(title="🪙 Coin Flip", color=discord.Color.gold())
    
    msg = await ctx.send(embed=discord.Embed(title="🪙 Flipping...", color=discord.Color.light_grey()))
    await asyncio.sleep(1)
    
    embed.description = f"**{result.upper()}**"
    await msg.edit(embed=embed)

# -------------------------
# Run the bot
# -------------------------
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