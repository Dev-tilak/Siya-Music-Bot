from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, Message, InlineKeyboardButton
from ANNIEMUSIC import app
import config
from ANNIEMUSIC.utils.decorators.language import language
from ANNIEMUSIC.utils.inline.help import first_page  # import help panel


# -------------------- EXISTING BUTTON PANELS -------------------- #
def start_panel(_):
    buttons = [
        [
            InlineKeyboardButton(
                text=_["S_B_1"],  # e.g. “Add Me”
                url=f"https://t.me/{app.username}?startgroup=true"
            ),
            InlineKeyboardButton(text=_["S_B_2"], url=config.SUPPORT_CHANNEL),
        ],
    ]
    return buttons


def private_panel(_):
    buttons = [
        [
            InlineKeyboardButton(
                text=_["S_B_1"],
                url=f"https://t.me/{app.username}?startgroup=true",
            )
        ],
        [
            InlineKeyboardButton(
                text=_["S_B_7"],
                url=f"https://t.me/{config.OWNER_USERNAME}"  # safer than user_id
            ),
            InlineKeyboardButton(text=_["S_B_4"], url=config.SUPPORT_CHAT),
        ],
        [
            InlineKeyboardButton(
                text=_["S_B_3"],
                callback_data="open_help"
            ),
        ],
    ]
    return buttons


# -------------------- /start COMMAND HANDLER -------------------- #

@app.on_message(filters.command("start") & filters.private)
@language
async def start_private(_, message: Message, __):
    """Show help menu when user starts bot in private chat."""
    await message.reply_text(
        text="🧭 **Help Menu**\n\nHere’s what I can do for you:",
        reply_markup=first_page(__)
    )


@app.on_message(filters.command("start") & filters.group)
@language
async def start_group(_, message: Message, __):
    """Show normal start panel when bot is used in a group."""
    await message.reply_text(
        text="👋 I'm online and ready! Use me to play music or manage the group.",
        reply_markup=InlineKeyboardMarkup(start_panel(__))
    )
