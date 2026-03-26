# 🚀 Dasixbot Hosting Services

Professional Discord bot hosting with full setup and management included. No technical knowledge required!

---

## 💎 Pricing Tiers

### **Tier 1 - Basic Hosting**
### $10/month

**What's Included:**
- ✅ 24/7 bot hosting on reliable servers
- ✅ Basic bot setup and configuration
- ✅ All core features enabled:
  - Moderation & anti-spam
  - Verification system
  - Support ticket system
  - Payment tracking
  - Giveaway system
  - Member stats channel
- ✅ Bot updates and maintenance
- ✅ Basic support via Discord

**Perfect for:** Small servers getting started with automation

---

### **Tier 2 - Advanced Hosting**
### $25/month

**Everything in Tier 1, plus:**
- ✅ Advanced bot configuration and customization
- ✅ Custom command prefix
- ✅ Personalized bot status message
- ✅ Custom anti-spam settings
- ✅ Custom embed colors and branding
- ✅ Multiple ticket categories tailored to your server
- ✅ Custom welcome messages
- ✅ Priority support response
- ✅ Weekly performance reports

**Perfect for:** Growing communities that need customization

---

### **Tier 3 - Premium Hosting + Website**
### $50/month

**Everything in Tier 2, plus:**
- ✅ **Fully functional website with live leaderboard**
- ✅ **Custom domain included** (yourserver.com)
- ✅ Real-time wager race tracking
- ✅ Professional leaderboard display
- ✅ Automatic stat updates from Dasixbot
- ✅ Responsive design (mobile-friendly)
- ✅ Custom branding and colors
- ✅ SSL certificate (secure HTTPS)
- ✅ Website hosting and maintenance
- ✅ VIP priority support (< 2 hour response)
- ✅ Monthly strategy consultation call

**Perfect for:** Established communities wanting a complete web presence

---

## 🎯 Feature Comparison

| Feature | Tier 1 | Tier 2 | Tier 3 |
|---------|--------|--------|--------|
| 24/7 Bot Hosting | ✅ | ✅ | ✅ |
| Basic Setup | ✅ | ✅ | ✅ |
| All Core Features | ✅ | ✅ | ✅ |
| Custom Configuration | ❌ | ✅ | ✅ |
| Custom Branding | ❌ | ✅ | ✅ |
| Priority Support | ❌ | ✅ | ✅ |
| Website Leaderboard | ❌ | ❌ | ✅ |
| Custom Domain | ❌ | ❌ | ✅ |
| Website Hosting | ❌ | ❌ | ✅ |
| Monthly Consultation | ❌ | ❌ | ✅ |

---

## 📋 All Tiers Include These Bot Features

### 🛡️ **Moderation & Security**
- Anti-spam system with auto-muting
- Verification system with code-based authentication
- Silent channels for announcement control
- Bulk message deletion

#### 🔇 Temp-Mute / Temp-Ban
- `!mute @user 10m Spamming` — automatically creates a `Muted` role with proper channel overwrites, stores active mutes in `tempmutes.json`, and auto-lifts them via a background task running every 15 seconds
- `!unmute @user` — manually lifts a mute before its timer expires
- `!tempban @user 1d Breaking rules` — bans the user and automatically unbans them after the specified duration using an async background task
- All punishments DM the user with the duration and reason

### 🖼️ **Welcome Image System**
- Generates a custom banner for each new member using Pillow — includes their circular avatar, username, member count, and server name
- Posts automatically to the welcome channel configured in `!setup` (Step 4: Welcome Channel)
- Gracefully falls back if Pillow is not installed or fonts are unavailable

### 💤 **AFK System**
- `!afk [reason]` — marks you as AFK and appends `[AFK]` to your nickname
- When another member pings an AFK user, the bot replies with their reason and how long they've been away
- AFK status is automatically removed the moment you send any message

### 📋 **Custom Commands**
- `!addcmd <trigger> <response>` — e.g. `!addcmd discord Join us at discord.gg/example` creates a `!discord` command anyone can use
- `!removecmd <trigger>` — deletes a custom command
- `!listcmds` — displays all active custom commands for the server
- Built-in bot commands are protected and cannot be overridden

### ⏱️ **Uptime**
- `!uptime` — displays how long the bot has been online, the exact start time, and current gateway latency

### 🎫 **Support Ticket System**
- Categorized support tickets with priorities
- Automatic HTML transcripts
- Ticket claiming and user management
- Professional ticket interface
- **Ticket Templates** — each category automatically sends a pre-filled question embed inside the ticket upon opening:
  - **Report** — asks for username, what they did, and evidence
  - **Technical** — asks for OS, error message, and steps already tried
  - Additional categories follow the same structured format
- **1–5 star rating system** — users are automatically sent a rating request via DM when their ticket closes
- **`!ticket_stats`** — staff can view total tickets, open/closed counts, average close time, average rating, and top categories

### 📊 **Utility Commands**
- **`!userinfo [member]`** — displays join date, account age, roles, avatar type, and full verification status
- **`!serverinfo`** — server overview with member count, channels, boosts, role count, emoji usage, and more
- **`!remindme <time> <message>`** — set personal reminders delivered via DM (supports `30m`, `1h`, `2h30m`, `1d`, etc.)

### 💰 **Payment Tracking**
- Track payments owed to team members
- Add, remove, and manage balances
- Visual payment dashboard
- Payment history logging

### 🎉 **Engagement Tools**

#### 🔴 Kick Live Announcements — `!live`
The `!live` command gives streamers a fully interactive flow to post a polished live notification to any Discord channel — no manual embed editing needed.

**How it works:**
1. A streamer with the `Streamer`, `Moderator`, `Developer`, `Support`, `Owner`, or `Administrator` role runs `!live`
2. A private button prompt appears — only visible to them
3. They click **Set Up Live Announcement** and enter their **Kick.com username**
4. They pick their **stream category** from a dropdown (Slots & Casino, Just Chatting, Gaming, Sports Betting, and more)
5. They select which **Discord channel** to post the notification in
6. The bot sends an `@everyone` embed with the stream category, a direct watch link, and a **Watch Stream** button — all in Kick green

All prompts are ephemeral (only visible to the command user), keeping your server clean.

#### 📢 Announcements — `!announce`
Now fully modal-based — no more manual embed editing.

**How it works:**
1. Click the **Make Announcement** button
2. Fill in the modal form:
   - **Title**
   - **Description**
   - **Color** — choose from blue, red, green, gold, purple, orange, teal, or white
   - **Image URL** (optional)
3. The bot posts a polished embed instantly

#### 🎉 Giveaway System — `!gstart`
The `!gstart` command launches an interactive giveaway modal so staff can run fully automated giveaways without any complex syntax.

**How it works:**
1. A user with the `Moderator`, `Developer`, `Support`, `Owner`, or `Administrator` role runs `!gstart`
2. A **Configure Giveaway** button appears (ephemeral, only visible to them)
3. They fill in a modal with three fields: **Duration** (e.g. `10s`, `30m`, `2h`, `1d`), **Number of Winners**, and **Prize**
4. The bot posts a public giveaway embed with a countdown timestamp and a 🎉 reaction entry button
5. When the timer expires, the bot automatically picks the winner(s) at random from all reactor users, mentions them publicly, and updates the embed

If there aren't enough entrants for the specified winner count, the bot gracefully ends the giveaway and notifies the channel.

- Coin flip game
- Custom server rules display
- Professional announcements
- Auto-updating member count

### ⚙️ **Server Management**
- Per-server configuration
- Easy setup wizard
- Stats channel with live member count
- Automatic bot updates

---

## 📝 Recent Updates

### v1.4.0 — March 2026
- ✨ Added `!mute` / `!unmute` — temp-mute system with auto-lift, role creation, and DM notifications
- ✨ Added `!tempban` — timed ban with automatic unban via async background task
- ✨ Added Welcome Image System — Pillow-generated banners with avatar, username, member count, and server name
- ✨ Added `!afk` — AFK status with nickname tagging, ping replies, and auto-removal on message
- ✨ Added `!addcmd` / `!removecmd` / `!listcmds` — per-server custom command manager with built-in command protection
- ✨ Added `!uptime` — shows bot uptime, start time, and current latency
- ✨ Improved `!announce` — now fully modal-based with title, description, color picker, and optional image URL
- ✨ Added Ticket Templates — pre-filled question embeds per category (Report, Technical, etc.)

### v1.3.0 — March 2026
- ✨ Added `!live` — interactive Kick.com live announcement system with username input, category picker, and channel selector
- ✨ Added `!gstart` — modal-driven giveaway system with automatic winner selection, reaction entry, and timed countdown

### v1.2.0 — March 2026
- ✨ Added `!userinfo` — detailed member profile with verification data
- ✨ Added `!serverinfo` — full server stats embed
- ✨ Added `!remindme` — personal DM reminders with persistent storage
- ✨ Added ticket rating system — automatic 1–5 star DM prompt on ticket close
- ✨ Added `!ticket_stats` — ticket analytics for staff (totals, avg close time, avg rating, top categories)
- 📖 Help menu expanded to 5 pages with all new commands documented

---

## 🚀 Getting Started

### Step 1: Choose Your Tier
Select the tier that best fits your community's needs.

### Step 2: We Handle Everything
- We set up the bot with your preferences
- We configure all features for your server
- We invite the bot to your Discord
- (Tier 3) We build and launch your website

### Step 3: You're Live!
Your bot is ready to use immediately. We provide:
- Complete walkthrough of all features
- Admin training for your team
- Documentation and support

### Step 4: Configure Your Welcome Channel
Run `!setup` and follow the prompts to designate a welcome channel. The bot will automatically post a generated welcome banner for every new member that joins.

---

## 💬 What Our Clients Say

> *"Went with Tier 3 and couldn't be happier. The leaderboard website makes our wager races so much more professional!"*  
> — Tliam155

> *"Perfect for our growing server. Setup took 10 minutes and support is always quick."*  
> — BLMKK

> *"The payment tracking alone is worth it. Keeps everything organized with our editors."*  
> — XHope

---

## 🔒 Why Choose Dasixbot Hosting?

✅ **No Technical Skills Needed** - We handle all the setup  
✅ **99.9% Uptime** - Reliable hosting infrastructure  
✅ **Secure & Private** - Your server data is protected  
✅ **Regular Updates** - New features added automatically  
✅ **Scalable** - Upgrade or downgrade anytime  
✅ **Cancel Anytime** - No long-term contracts  

---

## 📞 Ready to Get Started?

**Contact us to set up your bot today!**

📧 Email: support@dasixbot.xyz  
💬 Discord: [https://discord.gg/UwWbbyQ7pq]  
🌐 Website: [https://dasixbot.xyz]

### Special Launch Offer
**Get 1 month free when you sign up for Tier 3!**  
*Limited time offer - mention this when signing up*

---

## ❓ Frequently Asked Questions

**Q: Can I upgrade my tier later?**  
A: Yes! You can upgrade or downgrade at any time. Changes take effect immediately.

**Q: What if I have issues with the bot?**  
A: We provide support for all tiers. Tier 2 gets priority, and Tier 3 gets VIP priority with <2 hour response times.

**Q: Do you offer refunds?**  
A: Yes, we offer a 7-day money-back guarantee for first-time customers.

**Q: Can I use my own domain for Tier 3?**  
A: Absolutely! We can use your existing domain or help you get a new one.

**Q: How long does setup take?**  
A: Basic setup takes 10-30 minutes. Advanced customization (Tier 2) takes 1-2 hours. Full website deployment (Tier 3) takes 24-48 hours.

**Q: What payment methods do you accept?**  
A: We accept PayPal, credit/debit cards, and cryptocurrency.

---

*Pricing subject to change. All features and specifications accurate as of March 2026.*
