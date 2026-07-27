# Telegram Verification Forwarder

A lightweight, ultra-fast Pyrogram user bot that listens to the official Telegram service account (`777000`), instantly extracts verification codes, and pushes them to a Discord webhook. Includes a minimalist web dashboard for real-time monitoring.

## Features

- 🚀 **Instant Forwarding:** Automatically detects and forwards classic 5-digit codes and modern 11-character Web Login codes.
- ☁️ **Cloud-Native & Stateless:** Runs entirely in memory with no database or local storage dependencies. Designed to run flawlessly on ephemeral cloud hosts like Render.
- 📊 **Live Dashboard:** A lightweight Flask web interface to monitor real-time RAM/CPU usage and bot status (featuring a cute animated cat).
- 🔒 **Simple Configuration:** 100% driven by environment variables. No complicated CLI tools or config files required.

---

## Configuration

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

## Getting your Session String

Because the bot runs headlessly on the cloud, you need to generate an authentication session string on your local machine first. 

1. Clone this repository locally.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the session generator:
   ```bash
   python generate_session.py
   ```
4. Follow the interactive prompts to log in with your phone number and the OTP Telegram sends you. 
5. The script will output a long string. Copy this exact string and use it as your `TELEGRAM_SESSION_STRING` environment variable. **Keep it secret!**

---

## Deployment (Render)

This project is optimized for Render's Free Web Service tier.

1. Create a new **Web Service** on Render and connect this repository.
2. Under the **Environment** section, add your 4 required variables (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_STRING`, `DISCORD_WEBHOOK_URL`).
3. Deploy!

The application will start a Gunicorn server. The Pyrogram client runs securely in a background thread, pushing codes to Discord the moment they arrive. 

> **Note on Uptime:** Free cloud providers often sleep instances after inactivity. To keep the bot awake 24/7, point an external uptime monitor (like BetterStack or UptimeRobot) to your dashboard's root URL.