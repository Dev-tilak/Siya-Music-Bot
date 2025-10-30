import os
from random import randint
from typing import Union

from pyrogram.types import InlineKeyboardMarkup

import config
from ANNIEMUSIC import Carbon, YouTube, app
from ANNIEMUSIC.core.call import JARVIS
from ANNIEMUSIC.misc import db
from ANNIEMUSIC.utils.database import add_active_video_chat, is_active_chat
from ANNIEMUSIC.utils.exceptions import AssistantErr
from ANNIEMUSIC.utils.inline import aq_markup, close_markup, stream_markup
from ANNIEMUSIC.utils.pastebin import ANNIEBIN
from ANNIEMUSIC.utils.stream.queue import put_queue, put_queue_index
from ANNIEMUSIC.utils.thumbnails import get_thumb
from ANNIEMUSIC.utils.errors import capture_internal_err
from ANNIEMUSIC.platforms.Spotify import SpotifyAPI

spotify = SpotifyAPI()

import asyncio

async def delete_after_playback(file_path: str, duration: str):
    """Delete the file safely after the track finishes."""
    try:
        # Convert duration (mm:ss) → total seconds
        if duration and ":" in duration:
            parts = duration.split(":")
            seconds = int(parts[0]) * 60 + int(parts[1])
        else:
            seconds = 0  # skip live tracks or unknown durations

        # Wait for the song to complete (+ buffer)
        await asyncio.sleep(seconds + 30)

        # Delete the file if it exists
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[CLEANUP] Deleted file after playback: {file_path}")
        else:
            print(f"[CLEANUP] File not found (already removed?): {file_path}")

    except Exception as e:
        print(f"[CLEANUP ERROR] Could not delete {file_path}: {e}")



@capture_internal_err
async def stream(
    _,
    mystic,
    user_id,
    result,
    chat_id,
    user_name,
    original_chat_id,
    video: Union[bool, str] = None,
    streamtype: Union[bool, str] = None,
    # spotify_mode: Union[bool, str] = None,
    spotify: Union[bool, str] = None,
    forceplay: Union[bool, str] = None,
) -> None:
    if not result:
        return

    forceplay = bool(forceplay)
    is_video = bool(video)

    # ------------------------ 🧠 Helper Function ------------------------
    async def play_from_spotify(query):
        """Search the song in Spotify if YouTube fails."""
        print(f"[FALLBACK] YouTube failed — trying Spotify for: {query}")
        try:
            track_data, vidid = await spotify.search(query)
            if not track_data:
                print(f"[FALLBACK] No Spotify match found for {query}")
                return None

            title = track_data.get("title")
            duration_min = track_data.get("duration_min")
            thumb = track_data.get("thumb")

            # Download equivalent YouTube audio
            print(f"[FALLBACK] Downloading YouTube audio for Spotify track: {title}")
            file_path, direct = await YouTube.download(vidid, mystic)

            return {
                "title": title,
                "duration_min": duration_min,
                "thumb": thumb,
                "file_path": file_path,
                "direct": direct,
                "vidid": vidid,
            }
        except Exception as e:
            print(f"[FALLBACK ERROR] Spotify search or download failed: {e}")
            return None

    # ------------------------ 🎵 YouTube Stream ------------------------
    if streamtype == "youtube":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        duration_min = result["duration_min"]
        thumbnail = result["thumb"]

        print(f"[DEBUG] Attempting to stream YouTube track: {title}")

        try:
            file_path, direct = await YouTube.download(
                vidid, mystic, video=is_video, videoid=vidid
            )
        except Exception as e:
            print(f"[ERROR] YouTube download failed for {title}: {e}")
            print("[FALLBACK] Switching to Spotify...")
            spotify_track = await play_from_spotify(title)

            if not spotify_track:
                raise AssistantErr(f"❌ Could not fetch {title} from YouTube or Spotify.")

            file_path = spotify_track["file_path"]
            direct = spotify_track["direct"]
            title = spotify_track["title"]
            duration_min = spotify_track["duration_min"]
            thumbnail = spotify_track["thumb"]
            vidid = spotify_track["vidid"]

        if not file_path:
            raise AssistantErr(_["play_14"])

        # If chat is already playing, add to queue
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if is_video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await JARVIS.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=is_video,
                image=thumbnail,
            )
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if is_video else "audio",
                forceplay=forceplay,
            )
            img = await get_thumb(vidid)
            button = stream_markup(_, chat_id)
            run = await app.send_photo(
                original_chat_id,
                photo=img,
                caption=_["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(button),
            )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
        # Schedule file deletion after playback
            asyncio.create_task(delete_after_playback(file_path, duration_min))

    # ------------------------ 🎧 Spotify Stream ------------------------
    elif streamtype == "spotify":
        link = result.get("link")
        print(f"[DEBUG] Stream type: Spotify | Link: {link}")

        try:
            track_details, vidid = await spotify.track(link)
            print(f"[DEBUG] Spotify track details: {track_details}")

            title = track_details["title"]
            duration_min = track_details["duration_min"]
            thumb = track_details["thumb"]
            vidid = track_details["vidid"]

            # Download YouTube equivalent
            file_path, direct = await YouTube.download(vidid, mystic)

            if not file_path:
                raise AssistantErr(_["play_14"])

            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path if direct else f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "audio",
                )
                pos = len(db.get(chat_id)) - 1
                button = aq_markup(_, chat_id)
                await app.send_message(
                    chat_id=original_chat_id,
                    text=_["queue_4"].format(pos, title[:27], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )

            else:
                if not forceplay:
                    db[chat_id] = []
                await JARVIS.join_call(chat_id, original_chat_id, file_path, video=False, image=thumb)
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path if direct else f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "audio",
                    forceplay=forceplay,
                )
                img = await get_thumb(vidid)
                button = stream_markup(_, chat_id)
                run = await app.send_photo(
                    original_chat_id,
                    photo=img,
                    caption=_["stream_1"].format(
                        f"https://t.me/{app.username}?start=info_{vidid}",
                        title[:23],
                        duration_min,
                        user_name,
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"

        except Exception as e:
            print("[DEBUG] Spotify error:", e)
            raise AssistantErr(_["play_14"])
        asyncio.create_task(delete_after_playback(file_path, duration_min))

    # 🪄 Add the same logic to other sources (SoundCloud, Telegram, etc.)
    # if needed — only the YouTube block needed fallback to Spotify.
    elif streamtype == "soundcloud":
            file_path = result["filepath"]
            title = result["title"]
            duration_min = result["duration_min"]
            if not file_path:
                raise AssistantErr(_["play_14"])

            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path,
                    title,
                    duration_min,
                    user_name,
                    streamtype,
                    user_id,
                    "audio",
                )
                position = len(db.get(chat_id)) - 1
                button = aq_markup(_, chat_id)
                await app.send_message(
                    chat_id=original_chat_id,
                    text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                if not forceplay:
                    db[chat_id] = []
                await JARVIS.join_call(chat_id, original_chat_id, file_path, video=False)
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path,
                    title,
                    duration_min,
                    user_name,
                    streamtype,
                    user_id,
                    "audio",
                    forceplay=forceplay,
                )
                button = stream_markup(_, chat_id)
                run = await app.send_photo(
                    original_chat_id,
                    photo=config.SOUNCLOUD_IMG_URL,
                    caption=_["stream_1"].format(
                        config.SUPPORT_CHAT, title[:23], duration_min, user_name
                    ),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"
                asyncio.create_task(delete_after_playback(file_path, duration_min))

    elif streamtype == "telegram":
            file_path = result["path"]
            link = result["link"]
            title = (result["title"]).title()
            duration_min = result["dur"]
            if not file_path:
                raise AssistantErr(_["play_14"])

            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path,
                    title,
                    duration_min,
                    user_name,
                    streamtype,
                    user_id,
                    "video" if is_video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                button = aq_markup(_, chat_id)
                await app.send_message(
                    chat_id=original_chat_id,
                    text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                if not forceplay:
                    db[chat_id] = []
                await JARVIS.join_call(chat_id, original_chat_id, file_path, video=is_video)
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path,
                    title,
                    duration_min,
                    user_name,
                    streamtype,
                    user_id,
                    "video" if is_video else "audio",
                    forceplay=forceplay,
                )
                if is_video:
                    await add_active_video_chat(chat_id)
                button = stream_markup(_, chat_id)
                run = await app.send_photo(
                    original_chat_id,
                    photo=config.TELEGRAM_VIDEO_URL if is_video else config.TELEGRAM_AUDIO_URL,
                    caption=_["stream_1"].format(link, title[:23], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"
                asyncio.create_task(delete_after_playback(file_path, duration_min))


    elif streamtype == "live":
            link = result.get("link")
            vidid = result.get("vidid")
            title = (result.get("title") or "Unknown Title").title()
            thumbnail = result.get("thumb")
            duration_min = "Live Track"

            log.debug(f"[LIVE STREAM] Starting live stream: {title} | link={link} | vidid={vidid}")

            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"live_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if is_video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                button = aq_markup(_, chat_id)
                await app.send_message(
                    chat_id=original_chat_id,
                    text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                log.debug(f"[LIVE STREAM] Added to queue: {title} (Position: {position})")

            else:
                if not forceplay:
                    db[chat_id] = []

                # ✅ Fetch the live video file path safely
                try:
                    n, file_path = await YouTube.video(link)
                    log.debug(f"[LIVE STREAM] YouTube.video() returned: n={n}, file_path={file_path}")
                except Exception as e:
                    log.exception(f"[LIVE STREAM] Error fetching video from YouTube.video(): {e}")
                    raise AssistantErr("Failed to fetch live video from YouTube")

                # ✅ Handle unexpected tuple or dict returns
                if isinstance(file_path, tuple):
                    log.warning(f"[LIVE STREAM] file_path returned as tuple: {file_path}")
                    if len(file_path) > 1:
                        file_path = file_path[1]  # Extract actual URL/path
                    else:
                        file_path = file_path[0]

                if not file_path:
                    log.error("[LIVE STREAM] No valid file_path returned.")
                    raise AssistantErr(_["play_14"])

                log.debug(f"[LIVE STREAM] Joining call with file_path={file_path}")

                # ✅ Join the group voice call
                await JARVIS.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=is_video,
                    image=thumbnail or None,
                )

                # ✅ Add to playback queue
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"live_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if is_video else "audio",
                    forceplay=forceplay,
                )

                # ✅ Generate and send thumbnail
                try:
                    img = await get_thumb(vidid)
                except Exception as e:
                    log.warning(f"[LIVE STREAM] Thumbnail fetch failed: {e}")
                    img = None

                button = stream_markup(_, chat_id)
                try:
                    run = await app.send_photo(
                        original_chat_id,
                        photo=img if img else thumbnail,
                        caption=_["stream_1"].format(
                            f"https://t.me/{app.username}?start=info_{vidid}",
                            title[:23],
                            duration_min,
                            user_name,
                        ),
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                    db[chat_id][0]["mystic"] = run
                    db[chat_id][0]["markup"] = "tg"
                    log.info(f"[LIVE STREAM] Live stream started successfully: {title}")
                    asyncio.create_task(delete_after_playback(file_path, duration_min))
                except Exception as e:
                    log.exception(f"[LIVE STREAM] Error sending live stream photo: {e}")
                
    elif streamtype == "index":
            link = result
            title = "ɪɴᴅᴇx ᴏʀ ᴍ3ᴜ8 ʟɪɴᴋ"
            duration_min = "00:00"

            if await is_active_chat(chat_id):
                await put_queue_index(
                    chat_id,
                    original_chat_id,
                    "index_url",
                    title,
                    duration_min,
                    user_name,
                    link,
                    "video" if is_video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                button = aq_markup(_, chat_id)
                await mystic.edit_text(
                    text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                if not forceplay:
                    db[chat_id] = []
                await JARVIS.join_call(
                    chat_id,
                    original_chat_id,
                    link,
                    video=is_video,
                )
                await put_queue_index(
                    chat_id,
                    original_chat_id,
                    "index_url",
                    title,
                    duration_min,
                    user_name,
                    link,
                    "video" if is_video else "audio",
                    forceplay=forceplay,
                )
                button = stream_markup(_, chat_id)
                run = await app.send_photo(
                    original_chat_id,
                    photo=config.STREAM_IMG_URL,
                    caption=_["stream_2"].format(user_name),
                    reply_markup=InlineKeyboardMarkup(button),
                )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "tg"
                await mystic.delete()

