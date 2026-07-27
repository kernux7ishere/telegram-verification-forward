# Telegram Verification Forwarder

A lightweight, ultra-fast Pyrogram user bot that listens to the official Telegram service account (`777000`), instantly extracts verification codes, and pushes them to a Discord webhook. Includes a minimalist web dashboard for real-time monitoring.

## ✨ Features

- **Instant Forwarding:** Automatically detects and forwards classic 5-digit codes and modern 11-character Web Login codes.
- **Cloud-Native & Stateless:** Runs entirely in memory with no database or local storage dependencies. Designed to run flawlessly on ephemeral cloud hosts like Render.
- **Live Dashboard:** A lightweight Flask web interface to monitor real-time RAM/CPU usage and bot status (featuring a cute animated cat).
- **Simple Configuration:** 100% driven by environment variables. No complicated CLI tools or config files required.

---

## ⚙️ Configuration

Set the following environment variables in your hosting provider's dashboard:

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_API_ID` | **yes** | Your API ID from [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | **yes** | Your API Hash from [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_SESSION_STRING` | **yes** | Auth session string (generated locally) |
| `DISCORD_WEBHOOK_URL` | **yes** | The target Discord channel webhook URL |
| `PORT` | no | Dashboard port (default: 5000) |
| `RUN_WEBUI` | no | Set `false` to disable the Flask dashboard and run bot-only |

---

## 🔑 Getting your Session String

Because the bot runs headlessly on the cloud, you need to generate an authentication session string on your local machine first. 

1. 📥 Clone this repository locally.
2. 📦 Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. 🏃 Run the session generator:
   ```bash
   python generate_session.py
   ```
4. 📱 Follow the interactive prompts to log in with your phone number and the OTP Telegram sends you. 
5. 📝 The script will output a long string. Copy this exact string and use it as your `TELEGRAM_SESSION_STRING` environment variable. **Keep it secret!**

---

## 🚀 Deployment (Render)

This project is optimized for Render's Free Web Service tier.

1. ☁️ Create a new **Web Service** on Render and connect this repository.
2. ⚙️ Under the **Environment** section, add your required variables (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_STRING`, `DISCORD_WEBHOOK_URL`).
3. 🚀 Deploy!

The application will start a web server and run the Pyrogram client securely in a background thread, pushing codes to Discord the moment they arrive. 

---

## ⏰ Keeping the Bot Awake 24/7 (Important)

Free cloud providers like Render will put your instance to sleep if nobody visits the dashboard for 15 minutes. **When it goes to sleep, the bot shuts down and you will miss verification codes.**

To keep the bot awake permanently for free, you need to set up a service that automatically "visits" your dashboard every few minutes.

**Step-by-step setup:**
1. Sign up for a free uptime monitoring service like [UptimeRobot](https://uptimerobot.com/) or [BetterStack](https://betterstack.com/).
2. Create a new **HTTP Monitor** (or "Website Ping").
3. Paste the URL of your Render dashboard (e.g., `https://telegram-forwarder-....onrender.com`).
4. Set the ping interval to **5 minutes**.

The monitor will secretly "visit" your dashboard every 5 minutes, tricking Render into keeping the bot permanently awake.