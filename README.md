# 🤖 Multi-Purpose Discord Bot

A feature-rich, public Discord bot with moderation, verification, tickets, payments tracking, giveaways, and more!

## ✨ Features

### 🛡️ **Moderation & Security**
- **Anti-Spam System**: Automatically detects and mutes spammers
- **Verification System**: Secure code-based verification for new members
- **Silent Channels**: Channels where only admins can trigger @everyone notifications
- **Message Deletion**: Bulk delete messages

### 🎫 **Support System**
- **Advanced Ticket System**: Create categorized support tickets with priorities
- **Ticket Transcripts**: Automatically generate HTML transcripts when tickets close
- **Ticket Management**: Claim, prioritize, add users to tickets

### 💰 **Payment Tracking**
- Track payments owed to team members
- Add, remove, and manage payment balances
- Visual payment dashboard

### 🎉 **Engagement Features**
- **Giveaway System**: Host timed giveaways with multiple winners
- **Coin Flip**: Simple heads/tails game
- **Custom Rules**: Display server rules
- **Announcements**: Create formatted announcements

### ⚙️ **Server Management**
- **Interactive Setup**: Easy server configuration wizard
- **Stats Channel**: Auto-updating member count in voice channel
- **Per-Server Configuration**: Each server has its own settings

## 🚀 Setup Instructions

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token ([Get one here](https://discord.com/developers/applications))

### Installation

1. **Clone or download the bot files**

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure the bot**
   - Copy `.env.example` to `.env`
   - Add your Discord bot token:
```env
DISCORD_BOT_TOKEN=your_bot_token_here
```

4. **Enable necessary bot intents**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Select your bot
   - Go to "Bot" section
   - Enable these Privileged Gateway Intents:
     - ✅ PRESENCE INTENT
     - ✅ SERVER MEMBERS INTENT
     - ✅ MESSAGE CONTENT INTENT

5. **Invite the bot to your server**
   - Use this URL (replace YOUR_BOT_ID with your actual bot ID):
   ```
   https://discord.com/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot
   ```

6. **Run the bot**
```bash
python public_discord_bot.py
```

## 📋 Command List

### Basic Commands (Everyone)
- `!help` - Display all commands
- `!rules` - Show server rules
- `!ticket` - Create a support ticket
- `!flip` - Flip a coin
- `!pay_list` - View payment balances

### Setup (Administrator Only)
- `!setup` - Interactive server configuration wizard
  - Set verified role
  - Set announcement channel
  - Set stats voice channel

### Moderation (Administrator)
- `!delete <number>` - Delete specified number of messages
- `!announcement` - Create an announcement
- `!verify [member]` - Manually verify a member
- `!sendverify` - Post verification button

### Anti-Spam (Administrator)
- `!spam_info` - View current spam settings
- `!spam_config <msgs> <interval> <timeout>` - Configure spam detection
- `!unmute_user <member>` - Manually unmute a user

### Silent Channels (Administrator)
- `!silent_channels` - View all silent channels
- `!enable_silent [channel]` - Make a channel silent by default
- `!disable_silent [channel]` - Disable silent mode

### Payment Tracking (Administrator)
- `!pay_add <username> <amount>` - Add amount owed
- `!pay <username> <amount>` - Record a payment (subtracts from balance)
- `!pay_remove <username>` - Remove someone from tracker
- `!pay_reset` - Reset all payment data (with confirmation)

### Giveaways (Administrator)
- `!gstart <duration> <winners> <prize>` - Start a giveaway
  - Example: `!gstart 1h 2 $100 Prize`
  - Duration format: `10s`, `30m`, `1h`, `2d`

## 🎫 Ticket System

### For Users:
1. Use `!ticket` command to see the support button
2. Click "Create Ticket"
3. Select a category
4. Fill out the form with title and details
5. A private channel will be created for you

### For Staff:
- **Claim**: Click "✋ Claim" to assign yourself
- **Priority**: Click "⚠️ Priority" to change urgency
- **Add User**: Click "📋 Add User" to add someone to the ticket
- **Close**: Click "🔒 Close" to close and generate transcript

Transcripts are automatically saved to the `#ticket-logs` channel.

## 🔐 Verification System

### Setup:
1. Run `!setup` and set a verified role
2. Run `!sendverify` in your verification channel

### How it works:
1. New members click the "Verify" button
2. They receive a 6-digit code via DM (or privately if DMs are closed)
3. They type the code in the verification channel
4. The code is automatically deleted for security
5. They receive the verified role

### Features:
- Account age checking
- Risk level assessment
- Suspicious account logging
- Auto-welcome messages

## 🔕 Silent Channels

Silent channels are channels where:
- Regular users **cannot** trigger @everyone notifications
- Only **administrators** can ping @everyone
- Admin messages automatically add @everyone

**Use case**: Announcement channels where you don't want members spamming notifications

**Setup**:
```
!enable_silent #your-channel
```

## 💰 Payment Tracking

Perfect for tracking payments to editors, moderators, or team members.

**Example workflow**:
```
!pay_add John $500          # John is now owed $500
!pay_add John $200          # John is now owed $700
!pay John $300              # Paid John $300, now owed $400
!pay John $400              # Paid John $400, balance cleared!
```

## ⚙️ Configuration

Each server gets its own configuration stored in `server_config.json`:

```json
{
  "123456789": {
    "verified_role_id": 987654321,
    "announcement_channel_id": 876543210,
    "stats_channel_id": 765432109
  }
}
```

Run `!setup` to easily configure your server.

## 📊 Member Stats

Set up a voice channel to display your server's member count:
1. Create a voice channel
2. Lock it so members can't join
3. Run `!setup` and provide the channel
4. The bot will update it every 10 minutes: "📊 Members: 1,234"

## 🛡️ Anti-Spam System

Default settings:
- **5 messages** per **5 seconds** = **5 minute mute**

Customize with:
```
!spam_config 5 5 300
```

Features:
- Automatic message deletion
- DM notification to spammer
- Staff alert in channel
- Mod logging

## 📁 File Structure

```
.
├── public_discord_bot.py       # Main bot file
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
├── .env                       # Your config (create this)
├── payments.json              # Payment data (auto-created)
├── tickets.json               # Ticket data (auto-created)
├── verifications.json         # Verification data (auto-created)
└── server_config.json         # Server configs (auto-created)
```

## 🔧 Troubleshooting

### Bot won't start
- Check your token in `.env`
- Ensure you have Python 3.8+
- Install dependencies: `pip install -r requirements.txt`

### Verification not working
- Run `!setup` and configure the verified role
- Make sure the bot has permission to manage roles
- Ensure the bot's role is **above** the verified role

### Commands not responding
- Ensure Message Content Intent is enabled
- Check bot permissions in the server
- Make sure you're using the correct prefix: `!`

### Stats channel not updating
- Make sure the channel is a **voice channel**
- The bot needs permission to manage the channel
- Updates happen every 10 minutes

## 🔒 Security Notes

- **Never share your bot token**
- Keep your `.env` file private
- The bot uses DNS override for connection stability
- Verification codes expire in 15 minutes
- Failed verification attempts are limited to 3

## 📝 Customization

### Change Command Prefix
Line 140:
```python
bot = commands.Bot(command_prefix="!", intents=intents)
```

### Change Anti-Spam Settings
Line 151-155:
```python
anti_spam = AntiSpamSystem(
    messages_per_interval=5,
    interval_seconds=5,
    timeout_seconds=300
)
```

### Change Bot Status
Line 238:
```python
await bot.change_presence(activity=discord.Game(name="!help | Multi-Server Bot"))
```

## 🤝 Support

Need help? Have suggestions?
- Create an issue on GitHub
- Join our support server: [https://discord.gg/PMDtKbUfEA]

## 📜 License

This bot is provided as-is for public use. Feel free to modify and distribute.

## 🌟 Features Coming Soon

- [ ] Moderation logs
- [ ] Starboard system
- [ ] Custom welcome messages
- [ ] Reaction roles
- [ ] Auto-moderation (links, profanity, etc.)
- [ ] Music player
- [ ] Economy system
- [ ] Leveling system

## 📊 Bot Statistics

Track your bot's performance:
- Multi-server support ✅
- Per-server configuration ✅
- Persistent data storage ✅
- Auto-reconnection ✅
- Error handling ✅

---

**Made with ❤️ for the Discord community**

*This bot is not affiliated with any casino, gambling site, or commercial entity. It's a free, public bot for community use.*
