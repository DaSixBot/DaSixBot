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

#### 🔇 Temp-Mute / Temp-Ban
- `!mute @user 10m Spamming` — automatically creates a `Muted` role with proper channel overwrites, stores active mutes in `tempmutes.json`, and auto-lifts them via a background task running every 15 seconds
- `!unmute @user` — manually lifts a mute before its timer expires
- `!tempban @user 1d Breaking rules` — bans the user and automatically unbans them after the specified duration using an async background task
- All punishments DM the user with the duration and reason

#### ⚠️ Warning System
- `!warn @user [reason]` — issues a formal warning with escalating automatic punishments:
  - **3 warnings** → 1-hour auto-mute
  - **5 warnings** → 24-hour auto-mute
  - **7 warnings** → automatic kick
  - **10 warnings** → permanent ban
- `!warnings [@user]` — view all warnings for yourself or another member (last 10 shown), including what the next punishment threshold is
- `!clearwarns @user` — clear all warnings; `!clearwarns @user 2` — remove a specific warning by number
- Warned users receive a DM explaining what they were warned for and what happens next
- All punishments are logged to the audit channel automatically

#### 🐢 Slowmode
- `!slowmode 30s` — set slowmode on the current channel
- `!slowmode 5m #general` — set slowmode on a specific channel
- `!slowmode off` — disable slowmode
- Maximum: 6 hours (Discord limit). Every change is logged to the audit channel.

#### 🔕 Silent Channels
- `!enable_silent [#channel]` — prevent @everyone / @here pings from non-admins in a channel
- `!disable_silent [#channel]` — restore normal notification behavior
- `!silent_channels` — view all channels currently in silent mode

#### 🤖 Anti-Spam
- Automatically mutes users who send too many messages too quickly
- `!spam_info` — view current thresholds and all currently muted users
- `!spam_config <messages> <interval_seconds> <timeout_seconds>` — adjust thresholds live
- `!unmute_user @user` — manually lift an anti-spam mute

#### 🗑️ Bulk Delete
- `!delete <number>` — purge messages from the current channel

---

### 📋 **Audit Log System**

Set a dedicated channel with `!setauditlog #channel` and the bot will automatically log every server event:

| Event | What Gets Logged |
|-------|-----------------|
| ✏️ Message Edit | Before and after content, user, channel, jump link |
| 🗑️ Message Delete | Full message content, attachments, user, channel |
| 📥 Member Join | Username, account age, join timestamp, member count |
| 📤 Member Leave | Username, roles held at time of leaving |
| 🎭 Role Changes | Which roles were added or removed and to whom |
| ✏️ Nickname Change | Old and new nickname |
| 🔨 Ban / Unban | User ID and name |
| 🐢 Slowmode Change | Channel, new delay, who changed it |
| ⚠️ Warn / Auto-Punish | Reason, warn count, punishment applied |
| 🔇 Mute / Temp-Ban | Duration, reason, moderator |

Also configurable via the `!setup` wizard (Step 5).

---

### 📅 **Scheduled Announcements**

- `!schedule #channel 2h Your message here` — fire an announcement to any channel after any delay
  - Add `--everyone` at the end to ping @everyone automatically
  - Supports all time formats: `30s`, `10m`, `2h`, `1d`, `1h30m`
  - Minimum: 30 seconds · Maximum: 30 days
  - Scheduled announcements **survive bot restarts** (stored in `scheduled_announcements.json`)
- `!schedule_list` — view all pending scheduled announcements for your server
- `!schedule_cancel <number>` — cancel a pending announcement by its list number

---

### 🎫 **Support Ticket System**

#### Creating Tickets
- Interactive category dropdown with 6 categories: General Support, Technical Support, Account Issues, Report User/Issue, Suggestion, General Question
- Each category sends a pre-filled question template inside the ticket so users know exactly what info to provide
- Ticket embed shows priority, status, issue details, and the auto-close countdown

#### Ticket Controls (Staff)
- **✋ Claim** — assigns the ticket to a staff member, updates status to Claimed
- **🔒 Close** — generates an HTML transcript, posts it to `#ticket-logs`, DMs the user a copy, then deletes the channel
- **📋 Add User** — add any server member to the ticket by ID or @mention
- **⚠️ Priority** — set Low / Medium / High / Critical priority

#### Auto-Close System
- Tickets automatically close after **24 hours** of the **opener** not replying
- Staff replies do **not** reset the timer — only the opener's messages do
- The opener receives a DM warning before the channel is deleted
- Change the idle threshold by editing `TICKET_IDLE_HOURS` in `bot.py`

#### Rating System
- When a ticket closes, the opener automatically receives a 1–5 star DM rating prompt
- Ratings are stored and factored into `!ticket_stats`

#### Analytics
- `!ticket_stats` — full dashboard for staff: total tickets, open/closed counts, average close time, average rating, top categories, and auto-close threshold

---

### 🖼️ **Welcome Image System**
- Generates a custom banner for each new member using Pillow — includes their circular avatar, username, member count, and server name
- Posts automatically to the welcome channel configured in `!setup` (Step 4)
- Gracefully falls back to a plain embed if Pillow is unavailable

---

### 💤 **AFK System**
- `!afk [reason]` — marks you as AFK and appends `[AFK]` to your nickname
- When another member pings an AFK user, the bot replies with their reason and how long they've been away
- AFK status is automatically removed the moment you send any message
- AFK status is visible in `!userinfo`

---

### 📋 **Custom Commands**
- `!addcmd <trigger> <response>` — e.g. `!addcmd discord Join us at discord.gg/example` creates a `!discord` command anyone can use
- `!removecmd <trigger>` — deletes a custom command
- `!listcmds` — displays all active custom commands for the server
- Built-in bot commands are protected and cannot be overridden

---

### ⏱️ **Uptime**
- `!uptime` — displays how long the bot has been online, the exact start time, and current gateway latency

---

### 📊 **Utility Commands**
- `!userinfo [member]` — displays join date, account age, roles, avatar type, verification status, **warning count**, and AFK status
- `!serverinfo` — server overview with member count, channels, boosts, role count, emoji usage, and more
- `!remindme <time> <message>` — set personal reminders delivered via DM (supports `30m`, `1h`, `2h30m`, `1d`, etc.)

---

### 💰 **Payment Tracking**
- `!pay_add <username> <amount>` — add an amount owed to a team member
- `!pay <username> <amount>` — record a payment made
- `!pay_remove <username>` — remove a user from the tracker
- `!pay_list` — visual payment dashboard sorted by balance
- `!pay_reset` — reset all payment data (requires confirmation)

---

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

#### 📢 Announcements — `!announcement`
Now fully modal-based — no more manual embed editing.

**How it works:**
1. Click the **Make Announcement** button
2. Fill in the modal form:
   - **Title**
   - **Description**
   - **Color** — choose from blue, red, green, gold, purple, orange, teal, or white
   - **Image URL** (optional)
3. The bot posts a polished embed to the configured announcement channel, pinging @everyone

#### 📅 Scheduled Announcements — `!schedule`
Schedule any announcement to fire at a future time. Supports @everyone pings and survives bot restarts. See the **Scheduled Announcements** section above for full details.

#### 🎉 Giveaway System — `!gstart`
The `!gstart` command launches an interactive giveaway modal so staff can run fully automated giveaways without any complex syntax.

**How it works:**
1. A user with the `Moderator`, `Developer`, `Support`, `Owner`, or `Administrator` role runs `!gstart`
2. A **Configure Giveaway** button appears (ephemeral, only visible to them)
3. They fill in a modal with three fields: **Duration** (e.g. `10s`, `30m`, `2h`, `1d`), **Number of Winners**, and **Prize**
4. The bot posts a public giveaway embed with a countdown timestamp and a 🎉 reaction entry button
5. When the timer expires, the bot automatically picks the winner(s) at random from all reactor users, mentions them publicly, and updates the embed

If there aren't enough entrants for the specified winner count, the bot gracefully ends the giveaway and notifies the channel.

---

### 🔐 **Verification System**
- Button-based verification — users click **Verify** and receive a 6-digit code via DM
- Code is entered in the verification channel and auto-deleted
- 3 failed attempts locks the user out for 5 minutes
- Account age analysis flags new or suspicious accounts (risk levels: low / medium / high)
- `!verify [@member]` — manually verify a member (Admin only)
- `!sendverify` — post the verification button embed to a channel

---

### ⚙️ **Server Management**
- `!setup` — interactive 5-step wizard to configure: Verified Role, Announcement Channel, Stats Channel, Welcome Channel, **Audit Log Channel**
- `!setauditlog #channel` — standalone command to set or check the audit log channel
- Auto-updating member count channel (updates every 10 minutes)
- Per-server configuration stored in `server_config.json`

---

## 📝 Recent Updates

### v1.5.0 — April 2026
- ✨ Added **Warning System** — `!warn`, `!warnings`, `!clearwarns` with configurable escalating auto-punishments (mute → kick → ban)
- ✨ Added **Scheduled Announcements** — `!schedule`, `!schedule_list`, `!schedule_cancel` with @everyone support and restart-safe persistence
- ✨ Added **Audit Log System** — full event logging for message edits, deletes, joins, leaves, bans, role changes, nickname changes, slowmode, warns, and mutes
- ✨ Added `!slowmode` — set or disable slowmode on any channel with audit log integration
- ✨ Added **Ticket Auto-Close** — idle tickets close automatically after 24h of opener inactivity; staff replies don't reset the timer
- ✨ `!setup` expanded to 5 steps — now includes Audit Log Channel configuration
- ✨ `!userinfo` now shows warning count
- ✨ `!ticket_stats` now shows auto-close threshold

### v1.4.0 — March 2026
- ✨ Added `!mute` / `!unmute` — temp-mute system with auto-lift, role creation, and DM notifications
- ✨ Added `!tempban` — timed ban with automatic unban via async background task
- ✨ Added Welcome Image System — Pillow-generated banners with avatar, username, member count, and server name
- ✨ Added `!afk` — AFK status with nickname tagging, ping replies, and auto-removal on message
- ✨ Added `!addcmd` / `!removecmd` / `!listcmds` — per-server custom command manager with built-in command protection
- ✨ Added `!uptime` — shows bot uptime, start time, and current latency
- ✨ Improved `!announcement` — now fully modal-based with title, description, color picker, and optional image URL
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

### Step 4: Configure Your Server
Run `!setup` and follow the 5-step wizard to configure:
1. **Verified Role** — the role granted after verification
2. **Announcement Channel** — where `!announcement` posts
3. **Stats Channel** — auto-updates with member count every 10 minutes
4. **Welcome Channel** — receives the generated welcome banner on member join
5. **Audit Log Channel** — receives all server event logs

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

*Pricing subject to change. All features and specifications accurate as of April 2026.*
