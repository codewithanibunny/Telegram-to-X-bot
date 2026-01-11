import os
import asyncio
import logging
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import tweepy

TELEGRAM_BOT_TOKEN = 'TOKEN'
CHANNEL_ID = ID

X_API_KEY = 'API'
X_API_SECRET = 'SECRET'
X_ACCESS_TOKEN = 'ACCESS'
X_ACCESS_SECRET = 'ACESS SECRET'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

album_buffer = {}
processing_albums = set()

auth = tweepy.OAuth1UserHandler(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
x_api_v1 = tweepy.API(auth)
x_client_v2 = tweepy.Client(
    consumer_key=X_API_KEY,
    consumer_secret=X_API_SECRET,
    access_token=X_ACCESS_TOKEN,
    access_token_secret=X_ACCESS_SECRET
)

async def upload_media_to_x(file_path, is_video=False):
    loop = asyncio.get_running_loop()
    
    def _blocking_upload():
        try:
            if is_video:
                logger.info(f"Uploading video (chunked): {file_path}")
                media = x_api_v1.media_upload(filename=file_path, chunked=True, media_category='tweet_video')
                
                if hasattr(media, 'processing_info'):
                    info = media.processing_info
                    state = info['state']
                    while state in ['pending', 'in_progress']:
                        check_after_secs = info.get('check_after_secs', 1)
                        logger.info(f"Video processing... waiting {check_after_secs}s")
                        time.sleep(check_after_secs) # Blocks thread, not async loop
                        
                        status = x_api_v1.get_media_upload_status(media.media_id)
                        info = status.processing_info
                        state = info['state']
                    
                    if state == 'succeeded':
                        return media.media_id_string
                    else:
                        logger.error(f"Video processing failed: {info}")
                        return None
                else:
                    return media.media_id_string
            else:
                logger.info(f"Uploading image: {file_path}")
                media = x_api_v1.media_upload(filename=file_path)
                return media.media_id_string
        except Exception as e:
            logger.error(f"Error uploading media to X: {e}")
            return None

    return await loop.run_in_executor(None, _blocking_upload)

async def download_telegram_file(message, context):
    try:
        file_obj = None
        is_video = False
        
        if message.video:
            file_obj = message.video
            is_video = True
        elif message.photo:
            file_obj = message.photo[-1] # Highest resolution
        elif message.document:
            file_obj = message.document
            if 'video' in (message.document.mime_type or ''):
                is_video = True

        if not file_obj:
            return None, False

        # Check file size (limit is roughly 20MB for Bot API downloads)
        if file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
            logger.warning(f"File too large ({file_obj.file_size} bytes). Bot API limit is 20MB. Skipping.")
            return None, False

        # Get file info and download
        new_file = await context.bot.get_file(file_obj.file_id)
        
        # Create downloads folder
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
            
        file_name = f"downloads/{file_obj.file_unique_id}"
        if is_video:
            file_name += ".mp4"
        else:
            file_name += ".jpg"
            
        await new_file.download_to_drive(file_name)
        return file_name, is_video

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None, False

async def process_album_batch(media_group_id, context):
    if media_group_id not in album_buffer:
        return

    messages = album_buffer.pop(media_group_id)
    messages.sort(key=lambda x: x.message_id)

    caption = ""
    for msg in messages:
        if msg.caption:
            caption = msg.caption
            break
    
    # If no caption found, try to get text from messages
    if not caption:
        for msg in messages:
            if msg.text:
                caption = msg.text
                break

    media_ids = []
    temp_files = []

    try:
        # Download and Upload all media in the album
        for i, msg in enumerate(messages):
            file_path, is_video = await download_telegram_file(msg, context)
            if file_path:
                temp_files.append(file_path)
                logger.info(f"Album item {i+1}: Uploading {'video' if is_video else 'photo'}")
                media_id = await upload_media_to_x(file_path, is_video)
                if media_id:
                    media_ids.append(media_id)
                    logger.info(f"Album item {i+1}: Uploaded successfully (ID: {media_id})")
                else:
                    logger.error(f"Album item {i+1}: Failed to upload")

        # If there's no media and no caption, don't post anything
        if not media_ids and not caption:
            logger.warning(f"Album batch {media_group_id} has no media and no text. Skipping.")
            return

        # If there's caption but no media, post text-only tweet
        if not media_ids and caption:
            try:
                response = x_client_v2.create_tweet(text=caption)
                logger.info(f"Posted text-only tweet: {response.data['id']}")
            except Exception as e:
                logger.error(f"Failed to post text tweet: {e}")
            return

        # Posting to X with media - all items in one album (4 items max per post)
        logger.info(f"Album has {len(media_ids)} media items. Posting as album...")
        chunk_size = 4
        media_chunks = [media_ids[i:i + chunk_size] for i in range(0, len(media_ids), chunk_size)]
        previous_tweet_id = None

        for i, chunk in enumerate(media_chunks):
            text_to_send = caption if i == 0 else ""
            try:
                if previous_tweet_id:
                    response = x_client_v2.create_tweet(
                        text=text_to_send, media_ids=chunk, in_reply_to_tweet_id=previous_tweet_id
                    )
                else:
                    response = x_client_v2.create_tweet(text=text_to_send, media_ids=chunk)
                
                previous_tweet_id = response.data['id']
                logger.info(f"Posted tweet chunk {i+1}: {previous_tweet_id}")
            except Exception as e:
                logger.error(f"Failed to post chunk {i}: {e}")
                break

    finally:
        # Cleanup
        for f in temp_files:
            try:
                os.remove(f)
            except:
                pass
        if media_group_id in processing_albums:
            processing_albums.remove(media_group_id)

async def post_single_video(msg, context):
    try:
        caption = msg.caption or ""
        file_path, is_video = await download_telegram_file(msg, context)
        
        if not file_path:
            logger.error("Failed to download video")
            return
        
        try:
            media_id = await upload_media_to_x(file_path, is_video=True)
            if media_id:
                response = x_client_v2.create_tweet(text=caption, media_ids=[media_id])
                logger.info(f"Posted single video: {response.data['id']}")
            else:
                logger.error("Failed to upload video to X")
        finally:
            try:
                os.remove(file_path)
            except:
                pass
    except Exception as e:
        logger.error(f"Error posting single video: {e}")

async def post_single_photo(msg, context):
    try:
        caption = msg.caption or ""
        file_path, is_video = await download_telegram_file(msg, context)
        
        if not file_path:
            logger.error("Failed to download photo")
            return
        
        try:
            media_id = await upload_media_to_x(file_path, is_video=False)
            if media_id:
                response = x_client_v2.create_tweet(text=caption, media_ids=[media_id])
                logger.info(f"Posted single photo: {response.data['id']}")
            else:
                logger.error("Failed to upload photo to X")
        finally:
            try:
                os.remove(file_path)
            except:
                pass
    except Exception as e:
        logger.error(f"Error posting single photo: {e}")

async def post_text_only(msg, context):
    try:
        text = msg.text or ""
        if text:
            response = x_client_v2.create_tweet(text=text)
    except Exception as e:
        pass

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post or update.message
    if not msg:
        return

    if msg.media_group_id:
        grp_id = msg.media_group_id
        
        if grp_id not in album_buffer:
            album_buffer[grp_id] = []
            
            async def wait_and_process():
                await asyncio.sleep(5)
                await process_album_batch(grp_id, context)
            
            asyncio.create_task(wait_and_process())
        
        album_buffer[grp_id].append(msg)
    elif msg.video:
        await post_single_video(msg, context)
    elif msg.photo:
        await post_single_photo(msg, context)
    elif msg.text:
        await post_text_only(msg, context)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    handler = MessageHandler(
        filters.ChatType.CHANNEL & (filters.PHOTO | filters.VIDEO | filters.TEXT),
        channel_post_handler
    )
    
    application.add_handler(handler)

    application.run_polling()
