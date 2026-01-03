# 🚀 Quick Setup Guide

This guide will help you get your Discord bot up and running in under 10 minutes!

## 📋 Prerequisites

Before starting, make sure you have:
- A Discord account
- Python 3.8 or higher installed ([Download here](https://www.python.org/downloads/))
- Basic knowledge of using a terminal/command prompt

## 🔧 Step-by-Step Setup

### 1️⃣ Create Your Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"**
3. Give it a name (e.g., "MyServerBot")
4. Click **"Create"**

### 2️⃣ Configure Bot Settings

1. Click on **"Bot"** in the left sidebar
2. Click **"Add Bot"** → **"Yes, do it!"**
3. Under **"Privileged Gateway Intents"**, enable:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent
4. Click **"Save Changes"**

### 3️⃣ Get Your Bot Token

1. Still in the Bot section, find **"TOKEN"**
2. Click **"Reset Token"** → **"Yes, do it!"**
3. Click **"Copy"** to copy your token
4. ⚠️ **KEEP THIS SECRET!** Never share your token with anyone!

### 4️⃣ Install the Bot Files

1. Download all bot files to a folder on your computer
2. Open a terminal/command prompt in that folder
3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

### 5️⃣ Configure Your Bot

1. Rename `.env.example` to `.env`
2. Open `.env` in a text editor
3. Replace `your_bot_token_here` with your actual token:
   ```env
   DISCORD_BOT_TOKEN=YOUR_ACTUAL_TOKEN_HERE
   ```
4. Save the file

### 6️⃣ Invite Bot to Your Server

1. Go back to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Click **"OAuth2"** → **"URL Generator"**
4. Under **"Scopes"**, check:
   - ✅ bot
5. Under **"Bot Permissions"**, check:
   - ✅ Administrator (or select specific permissions)
6. Copy the generated URL at the bottom
7. Paste it in your browser and select your server
8. Click **"Authorize"**

### 7️⃣ Start Your Bot

In your terminal, run:
```bash
python public_discord_bot.py
```

You should see:
```
Logged in as YourBot (ID: 123456789)
Connected to 1 servers
[Bot] All background tasks started
```

🎉 **Your bot is now online!**

## ⚙️ Initial Server Configuration

Once your bot is online, run these commands in your Discord server:

### 1. Run Setup Wizard
```
!setup
```
Follow the prompts to configure:
- Verified role (for verification system)
- Announcement channel (for announcements)
- Stats voice channel (for member count display)

### 2. Set Up Verification (Optional)
```
!sendverify
```
Post this in your verification channel so members can verify themselves.

### 3. Set Up Support Tickets (Optional)
```
!ticket
```
Post this in a support channel so members can create tickets.

## 🧪 Test Your Bot

Try these commands to make sure everything works:

```
!help          # Should show all commands
!rules         # Should display server rules
!flip          # Should flip a coin
```

### Admin Commands to Test:
```
!spam_info     # View anti-spam settings
!pay_list      # View payment tracker (should be empty)
```

## 🎯 Common Issues & Solutions

### Bot is offline
- ✅ Check your token in `.env`
- ✅ Make sure you ran `python public_discord_bot.py`
- ✅ Check for error messages in the terminal

### Commands not working
- ✅ Make sure you're using `!` prefix (not `?` or `/`)
- ✅ Check that Message Content Intent is enabled
- ✅ Ensure bot has appropriate permissions

### "Missing Permissions" errors
- ✅ Make sure bot role is above other roles
- ✅ Check channel-specific permissions
- ✅ Grant Administrator permission (easiest solution)

### Verification not working
- ✅ Run `!setup` and configure verified role
- ✅ Make sure bot can manage roles
- ✅ Ensure verified role is below bot's role in hierarchy

## 📚 Next Steps

Now that your bot is running:

1. **Read the README.md** for detailed feature explanations
2. **Customize** the bot settings to your liking
3. **Test** all features in a test channel
4. **Announce** to your community that the bot is live!

## 🔐 Security Best Practices

- ✅ Never commit `.env` to GitHub
- ✅ Don't share your bot token
- ✅ Use environment variables for sensitive data
- ✅ Regularly update dependencies
- ✅ Keep backups of JSON data files

## 🆘 Getting Help

If you encounter issues:

1. Check this guide again
2. Read error messages carefully
3. Search for the error online
4. Check the bot's GitHub issues
5. Ask in our support server

## 🎓 Learn More

Want to understand how the bot works?
- Read through `public_discord_bot.py`
- Check out [discord.py documentation](https://discordpy.readthedocs.io/)
- Experiment with modifying features

---

## 🌟 Quick Reference Card

| Action | Command |
|--------|---------|
| Get help | `!help` |
| Setup bot | `!setup` |
| Post verification | `!sendverify` |
| Post ticket button | `!ticket` |
| Start giveaway | `!gstart 1h 1 Prize` |
| Delete messages | `!delete 10` |
| View spam settings | `!spam_info` |

---

**🚀 You're all set! Enjoy your new Discord bot!**