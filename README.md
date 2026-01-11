# Telegram to X (Twitter) Bot

A bot that listens to Telegram channel posts and automatically posts them to X (formerly Twitter).

## Features

- **Text Posts**: Direct posting of text messages to X
- **Single Photo Posts**: Upload and post individual photos
- **Single Video Posts**: Upload and post individual videos with chunked upload support
- **Album Posts**: Handle multi-media albums containing both photos and videos
- **Caption Support**: Preserves captions from Telegram posts
- **Automatic Cleanup**: Removes temporary files after posting

## Installation

1. Clone or download this repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Set your credentials in `bot.py`:

```python
TELEGRAM_BOT_TOKEN = 'your_telegram_bot_token'
CHANNEL_ID =   # Your Telegram channel ID

X_API_KEY = 'your_x_api_key'
X_API_SECRET = 'your_x_api_secret'
X_ACCESS_TOKEN = 'your_x_access_token'
X_ACCESS_SECRET = 'your_x_access_secret'
```

## How It Works

### Message Handling

The bot distinguishes between four types of posts:

1. **Album Posts** (media_group_id)
   - Messages with multiple media items grouped together
   - Waits 5 seconds for all items in the group to arrive
   - Posts all items as a single album on X (max 4 items per post)

2. **Single Video Posts**
   - Standalone video messages
   - Uses chunked upload for larger files
   - Includes caption if provided

3. **Single Photo Posts**
   - Standalone photo messages
   - Includes caption if provided

4. **Text-Only Posts**
   - Pure text messages without any media

### Media Upload

- **Videos**: Uploaded with chunked streaming, waits for processing to complete
- **Photos**: Direct upload as JPEG format
- **File Size Limit**: 20MB (Bot API limitation)

## Usage

1. Add the bot to your Telegram channel
2. Send posts to the channel
3. The bot will automatically post them to your X account

```bash
python bot.py
```

## File Structure

```
├── bot.py              # Main bot script
├── requirements.txt    # Python dependencies
├── channels_db.json    # Channel data (auto-generated)
├── users_db.json       # User data (auto-generated)
├── downloads/          # Temporary media storage
└── README.md          # This file
```

## Dependencies

- `python-telegram-bot`: Telegram Bot API client
- `tweepy`: Twitter/X API client
- `requests`: HTTP library

## Error Handling

The bot includes error handling for:
- Failed media downloads
- Upload failures
- Network errors
- Processing timeouts

## Notes

- Videos are limited to 20MB due to Telegram Bot API restrictions
- Albums are posted in chunks of up to 4 items
- Temporary files are automatically cleaned up after posting
- The bot runs in polling mode for continuous updates
