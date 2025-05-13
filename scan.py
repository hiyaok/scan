#
import os
import asyncio
import time
import json
import zipfile
import shutil
import random
import signal
import traceback
from datetime import datetime
from telethon.sync import TelegramClient
from telethon import events, Button, functions, errors
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import GetHistoryRequest, DeleteHistoryRequest
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.types import InputPeerUser, InputPeerChannel
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError, FloodWaitError
from telethon.errors.rpcerrorlist import AuthKeyError, PhoneNumberBannedError

# Bot configuration
API_ID = 25649945
API_HASH = "d91f3e307f5ee75e57136421f2c3adc6"
BOT_TOKEN = "7354445605:AAEyRju_l_T1y-tgHd4NgD-bVJseb3tGr_U"
ADMIN_ID = 5988451717

# Dictionary to track session files received from users
user_sessions = {}

# Dictionary to store active sessions
active_sessions = {}

# Dictionary to track current page for each user
user_current_page = {}

# File to store active sessions
SESSIONS_FILE = "active_sessions.json"

# OTP Sender entities
OTP_SENDERS = ["+42777", "777000", "telegram"]

# Temporary directory for zip extraction
TEMP_DIR = "temp_zip_extraction"

# Pending tasks set to properly manage asyncio tasks
pending_tasks = set()

# Create bot with proper connection parameters
bot = None

# Initialize the bot safely
async def init_bot():
    global bot
    try:
        # Add slightly longer timeout for reliability
        bot = TelegramClient('bot', API_ID, API_HASH, connection_retries=5, retry_delay=1)
        await bot.start(bot_token=BOT_TOKEN)
        print("Bot berhasil diinisialisasi")
        return True
    except Exception as e:
        print(f"Error saat inisialisasi bot: {e}")
        return False

# Helper function to create and track asyncio tasks
def create_task(coro):
    task = asyncio.create_task(coro)
    pending_tasks.add(task)
    task.add_done_callback(pending_tasks.discard)
    return task

# Load saved sessions from file
def load_sessions():
    global active_sessions
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'r') as f:
                active_sessions = json.load(f)
            print(f"Berhasil memuat {sum(len(sessions) for sessions in active_sessions.values())} session dari file")
        else:
            print("File session tidak ditemukan, membuat baru")
            active_sessions = {}
    except Exception as e:
        print(f"Error loading sessions: {e}")
        active_sessions = {}

# Save sessions to file
def save_sessions():
    try:
        with open(SESSIONS_FILE, 'w') as f:
            json.dump(active_sessions, f)
        print(f"Berhasil menyimpan {sum(len(sessions) for sessions in active_sessions.values())} session ke file")
    except Exception as e:
        print(f"Error saving sessions: {e}")

# Create temp directories if needed
def ensure_temp_dirs():
    try:
        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)
            print(f"Dibuat direktori sementara: {TEMP_DIR}")
    except Exception as e:
        print(f"Error creating temp directory: {e}")

# Clean up temporary files
def cleanup_temp_files():
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            print(f"Dibersihkan direktori sementara: {TEMP_DIR}")
        
        # Clean up any temp files in the current directory
        for filename in os.listdir('.'):
            if filename.startswith('temp_') or filename.endswith('.session'):
                try:
                    os.remove(filename)
                except:
                    pass
    except Exception as e:
        print(f"Error cleaning up temp files: {e}")

@events.register(events.NewMessage(pattern='/start'))
async def start(event):
    """Send a message when the command /start is issued."""
    await event.respond('Selamat datang di Session Checker Bot! Kirim file session Telegram atau file ZIP untuk dicheck.')

@events.register(events.NewMessage(pattern='/kelola'))
async def kelola(event):
    """Handle /kelola command to manage active sessions."""
    user_id = event.sender_id
    
    # Only allow admin to use the bot
    if user_id != ADMIN_ID:
        await event.respond("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
        return
    
    # Convert user_id to string for dictionary key
    user_id_str = str(user_id)
    
    # Get the current page for this user (default to 0)
    current_page = user_current_page.get(user_id_str, 0)
    
    if user_id_str in active_sessions and active_sessions[user_id_str]:
        # Create pagination for sessions
        await show_session_list(user_id, current_page)
    else:
        await event.respond("Gak ada session aktif nih. Check session dulu gih.")

async def show_session_list(user_id, page=0):
    """Show paginated list of active sessions."""
    try:
        user_id_str = str(user_id)
        # Store the current page for this user
        user_current_page[user_id_str] = page
        
        if user_id_str not in active_sessions or not active_sessions[user_id_str]:
            await bot.send_message(user_id, "Gak ada session aktif nih. Upload session dulu yuk.")
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
            message += f"{i+1}. **{session.get('first_name', 'Tidak diketahui')}** (@{session.get('username', 'tidak ada') or 'tidak ada'}) - `{session.get('phone', 'Tidak diketahui')}`\n"
        
        message += f"\nHalaman {page+1}/{total_pages}"
        
        # Create buttons for pagination and actions
        buttons = []
        
        # Add session buttons
        session_buttons = []
        for i in range(start_idx, end_idx):
            session = sessions[i]
            name = session.get('first_name', 'Unknown')
            phone = session.get('phone', 'No Phone')
            session_buttons.append([Button.inline(f"🔹 {name} ({phone})", f"session_{i}")])
        
        # Add navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(Button.inline("⬅️ Sebelumnya", f"page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(Button.inline("Selanjutnya ➡️", f"page_{page+1}"))
        
        buttons = session_buttons
        if nav_buttons:
            buttons.append(nav_buttons)
            
        # Add the invite contacts button if we have sessions
        if len(sessions) > 0:
            buttons.append([Button.inline("👥 Gas Invite Kontak ke Grup", "invite_contacts")])
        
        await bot.send_message(user_id, message, buttons=buttons)
    except Exception as e:
        print(f"Error in show_session_list: {e}")
        await bot.send_message(user_id, f"Waduh error nih: {str(e)}")

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"page_")))
async def handle_page_callback(event):
    """Handle pagination callbacks."""
    try:
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
    except Exception as e:
        print(f"Error in handle_page_callback: {e}")
        await event.answer(f"Duh, error nih: {str(e)}")

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"session_")))
async def handle_session_callback(event):
    """Handle session selection."""
    try:
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
                    Button.inline("🔄 Refresh Info", f"refresh_{session_idx}")
                ],
                [
                    Button.inline("🧹 Clear All Chats", f"clear_{session_idx}"),
                    Button.inline("🧼 Clear OTP Chats", f"clear_otp_{session_idx}")
                ],
                [
                    Button.inline("🗑️ Hapus", f"delete_{session_idx}"),
                    Button.inline("⬅️ Kembali", f"back_to_list_{user_current_page.get(user_id_str, 0)}")
                ]
            ]
            
            # Create more detailed session info message
            message = (
                f"✅ **DETAIL SESSION**\n\n"
                f"📱 **Nomor:** `{session.get('phone', 'Tidak diketahui')}`\n"
                f"👤 **Nama Depan:** `{session.get('first_name', 'Tidak diketahui')}`\n"
                f"👤 **Nama Belakang:** `{session.get('last_name', 'Tidak ada')}`\n"
                f"🔖 **Username:** `{session.get('username', 'Tidak ada')}`\n"
                f"🆔 **User ID:** `{session.get('user_id', 'Tidak diketahui')}`\n"
                f"📅 **Tanggal Pembuatan:** `{session.get('creation_date', 'Tidak diketahui')}`\n"
                f"🔐 **Premium:** `{session.get('is_premium', 'Tidak diketahui')}`\n"
                f"🔄 **2FA/Password:** `{'Ya' if session.get('has_2fa') == True else 'Tidak'}`\n"
                f"📨 **Status Terakhir:** `{session.get('last_status', 'Belum diketahui')}`\n"
            )
            
            await event.edit(message, buttons=buttons)
        else:
            await event.answer("Session nggak ketemu nih.")
    except Exception as e:
        print(f"Error in handle_session_callback: {e}")
        await event.answer(f"Waduh error: {str(e)}")

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"refresh_")))
async def refresh_session_info(event):
    """Refresh session information with more details."""
    try:
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
            
            # Create status message
            status_msg = await event.respond("⏳ Tunggu bentar, lagi update info nih...")
            
            # Get fresh session information
            fresh_info = await get_detailed_session_info(session)
            
            if fresh_info['success']:
                # Update the session info in storage
                for key, value in fresh_info['info'].items():
                    active_sessions[user_id_str][session_idx][key] = value
                
                # Save sessions
                save_sessions()
                
                # Get the updated session
                session = active_sessions[user_id_str][session_idx]
                
                # Create a more detailed message with the updated info
                message = (
                    f"✅ **DETAIL SESSION (FRESH UPDATE)**\n\n"
                    f"📱 **Nomor:** `{session.get('phone', 'Tidak diketahui')}`\n"
                    f"👤 **Nama Depan:** `{session.get('first_name', 'Tidak diketahui')}`\n"
                    f"👤 **Nama Belakang:** `{session.get('last_name', 'Tidak ada')}`\n"
                    f"🔖 **Username:** `{session.get('username', 'Tidak ada')}`\n"
                    f"🆔 **User ID:** `{session.get('user_id', 'Tidak diketahui')}`\n"
                    f"📅 **Tanggal Pembuatan:** `{session.get('creation_date', 'Tidak diketahui')}`\n"
                    f"⏰ **Terakhir Online:** `{session.get('last_online', 'Tidak diketahui')}`\n"
                    f"🔐 **Premium:** `{session.get('is_premium', 'Tidak diketahui')}`\n"
                    f"🔄 **2FA/Password:** `{'Ya' if session.get('has_2fa') == True else 'Tidak'}`\n"
                    f"🔑 **Password Hint:** `{session.get('password_hint', 'Tidak ada')}`\n"
                    f"📨 **Status Terakhir:** `{session.get('last_status', 'Aktif')}`\n"
                    f"🌐 **Verifikasi:** `{session.get('verified', 'Tidak diketahui')}`\n"
                    f"👥 **Jumlah Kontak:** `{session.get('contact_count', 'Tidak diketahui')}`\n"
                )
                
                # Create action buttons for the session
                buttons = [
                    [
                        Button.inline("📲 Get OTP", f"otp_{session_idx}"),
                        Button.inline("🔄 Refresh Info", f"refresh_{session_idx}")
                    ],
                    [
                        Button.inline("🧹 Clear All Chats", f"clear_{session_idx}"),
                        Button.inline("🧼 Clear OTP Chats", f"clear_otp_{session_idx}")
                    ],
                    [
                        Button.inline("🗑️ Hapus", f"delete_{session_idx}"),
                        Button.inline("⬅️ Kembali", f"back_to_list_{user_current_page.get(user_id_str, 0)}")
                    ]
                ]
                
                await status_msg.edit(message, buttons=buttons)
            else:
                await status_msg.edit(
                    f"❌ **GAGAL UPDATE INFO NIH**\n\n"
                    f"Pesan error: {fresh_info['error']}",
                    buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
                )
        else:
            await event.answer("Session nggak ketemu nih.")
    except Exception as e:
        print(f"Error in refresh_session_info: {e}")
        try:
            await event.answer(f"Ada error nih bro")
            await event.respond(f"Error: {str(e)}", buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")])
        except:
            pass

async def get_detailed_session_info(session):
    """Get detailed session information."""
    client = None
    session_path = f"temp_session_{session.get('user_id', 'unknown')}_{int(time.time())}.session"
    
    result = {'success': False, 'error': 'Error tidak diketahui', 'info': {}}
    
    try:
        # Try to create a client with the saved session data
        if not session.get('session_data'):
            return {'success': False, 'error': "Data session gak ada nih"}
            
        # Write session data to file
        with open(session_path, 'wb') as f:
            f.write(bytes.fromhex(session['session_data']))
        
        # Add a small delay to avoid connection errors
        await asyncio.sleep(1)
        
        # Connect to Telegram with better error handling
        client = TelegramClient(
            session_path.replace('.session', ''), 
            API_ID, 
            API_HASH, 
            connection_retries=5,
            retry_delay=2
        )
        
        # Connect with longer timeout
        try:
            await asyncio.wait_for(client.connect(), timeout=20)
        except asyncio.TimeoutError:
            return {'success': False, 'error': "Koneksi timeout nih"}
        
        # Wait after connection
        await asyncio.sleep(2)
        
        # Ensure we're connected and authorized
        if not await client.is_user_authorized():
            print(f"Session {session.get('phone')} tidak terotorisasi saat mencoba get details")
            # Try once more with forced reconnection
            await client.disconnect()
            await asyncio.sleep(2)
            await client.connect()
            await asyncio.sleep(1)
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': "Session gak valid, coba lagi nanti"}
        
        # Get detailed user info
        info = {}
        
        try:
            # Basic user info
            me = await client.get_me()
            info['user_id'] = me.id
            info['first_name'] = me.first_name
            info['last_name'] = me.last_name
            info['username'] = me.username
            info['phone'] = me.phone
            info['is_premium'] = "Ya" if getattr(me, 'premium', False) else "Tidak"
            info['verified'] = "Ya" if getattr(me, 'verified', False) else "Tidak"
            
            # Get more detailed info
            try:
                full_user = await client(GetFullUserRequest(me.id))
                info['about'] = getattr(full_user.full_user, 'about', 'Tidak ada')
                info['common_chats_count'] = getattr(full_user.full_user, 'common_chats_count', 0)
                
                # Check for password hint if available
                password_hint = getattr(full_user.full_user, 'password_hint', None)
                info['password_hint'] = password_hint if password_hint else 'Tidak ada'
                
                # Last online status
                last_online = getattr(me, 'status', None)
                if last_online:
                    if hasattr(last_online, 'was_online'):
                        info['last_online'] = last_online.was_online.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        info['last_online'] = 'Baru saja'
                else:
                    info['last_online'] = 'Tidak diketahui'
            except Exception as full_error:
                print(f"Error getting full user info: {full_error}")
                info['last_online'] = 'Tidak dapat diambil'
            
            # Check 2FA status
            info['has_2fa'] = False
            
            # Improved 2FA detection
            try:
                # Try with a small API call that requires 2FA when enabled
                try:
                    # This might trigger a password request if 2FA is enabled
                    await client.get_password_hint()
                    # If we reach here without exception, no 2FA is set
                except SessionPasswordNeededError:
                    info['has_2fa'] = True
                except:
                    # Another error occurred, unsure about 2FA
                    pass
            except:
                # Failed to check 2FA, keep current value
                info['has_2fa'] = session.get('has_2fa', False)
            
            # Count contacts
            try:
                # Use GetContactsRequest instead of iter_contacts
                from telethon.tl.functions.contacts import GetContactsRequest
                result = await client(GetContactsRequest(hash=0))
                info['contact_count'] = len(result.users)
            except Exception as e:
                print(f"Error counting contacts: {e}")
                info['contact_count'] = 'Tidak dapat diambil'
            
            # Mark session as active
            info['last_status'] = 'Aktif'
            
            # Update creation date if available
            try:
                timestamp = ((me.id >> 32) - 1420070400)
                if timestamp > 0:
                    info['creation_date'] = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            except:
                # Keep existing creation date if available
                if 'creation_date' in session:
                    info['creation_date'] = session['creation_date']
            
            return {'success': True, 'info': info}
            
        except Exception as e:
            print(f"Error getting detailed info: {e}")
            return {'success': False, 'error': f"Gagal ambil info: {str(e)}"}
    
    except FloodWaitError as e:
        print(f"FloodWaitError: {e}")
        return {'success': False, 'error': f"Telegram minta nunggu {e.seconds} detik"}
    except Exception as e:
        print(f"Error in get_detailed_session_info: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        # Ensure client is disconnected
        if client:
            try:
                await client.disconnect()
            except:
                pass
        
        # Clean up session file
        try:
            await asyncio.sleep(1)  # Small delay before cleanup
            if os.path.exists(session_path):
                os.remove(session_path)
            if os.path.exists(session_path.replace('.session', '') + '.session'):
                os.remove(session_path.replace('.session', '') + '.session')
        except Exception as e:
            print(f"Error cleaning up session files: {e}")

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"back_to_list_")))
async def back_to_list(event):
    """Go back to the session list at the specific page."""
    try:
        user_id = event.sender_id
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
            return
        
        # Get the page to return to
        page = int(event.data.decode().split("_")[3])
        
        await event.delete()
        await show_session_list(user_id, page)
    except Exception as e:
        print(f"Error in back_to_list: {e}")
        await event.answer(f"Waduh error nih: {str(e)}")

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"otp_")))
async def get_otp(event):
    """Get OTP for the selected session."""
    try:
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
            status_msg = await event.respond("⏳ Lagi nyari OTP terbaru...")
            
            # Try to get OTP
            otp_result = await get_latest_otp(session)
            
            if otp_result['success']:
                # Hanya tampilkan kode OTP saja, tanpa pesan lengkap
                await status_msg.edit(
                    f"✅ **KETEMU OTP NYA!**\n\n"
                    f"📱 **Untuk:** `{session.get('phone', 'Tidak diketahui')}`\n"
                    f"🔢 **Kode OTP:** `{otp_result['otp']}`\n"
                    f"⏰ **Waktu:** `{otp_result['time']}`\n"
                    f"📩 **Sumber:** `{otp_result.get('source', 'Pesan Telegram')}`",
                    buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
                )
            else:
                await status_msg.edit(
                    f"❌ **OTP GAK KETEMU NIH**\n\n"
                    f"Pesan: {otp_result['error']}",
                    buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
                )
        else:
            await event.answer("Session nggak ketemu.")
    except Exception as e:
        print(f"Error in get_otp: {e}")
        try:
            await event.answer(f"Ada error nih waktu nyari OTP")
            await event.respond(f"Error: {str(e)}", buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")])
        except:
            pass

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"clear_")))
async def clear_chat_history(event):
    """Clear chat history for the selected session."""
    try:
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
            status_msg = await event.respond("⏳ Lagi bersihin chat history...")
            
            # Try to clear chat history
            clear_result = await clear_chat_messages(session)
            
            if clear_result['success']:
                await status_msg.edit(
                    f"✅ **CHAT UDAH DIBERSIHIN**\n\n"
                    f"📱 **Untuk:** `{session.get('phone', 'Tidak diketahui')}`\n"
                    f"📊 **Jumlah Chat Dihapus:** `{clear_result.get('count', 'Tidak diketahui')}`",
                    buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
                )
            else:
                await status_msg.edit(
                    f"❌ **GAGAL HAPUS CHAT**\n\n"
                    f"Pesan: {clear_result['error']}",
                    buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
                )
        else:
            await event.answer("Session nggak ketemu.")
    except Exception as e:
        print(f"Error in clear_chat_history: {e}")
        try:
            await event.answer(f"Ada error nih waktu hapus chat")
            await event.respond(f"Error: {str(e)}", buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")])
        except:
            pass

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"clear_otp_")))
async def clear_otp_chat_history(event):
    """Clear chat history with OTP senders for the selected session."""
    try:
        user_id = event.sender_id
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
            return
        
        # Get selected session index
        session_idx = int(event.data.decode().split("_")[2])
        user_id_str = str(user_id)
        
        if user_id_str in active_sessions and 0 <= session_idx < len(active_sessions[user_id_str]):
            session = active_sessions[user_id_str][session_idx]
            
            # Create a status message
            status_msg = await event.respond("⏳ Lagi apus pesan OTP...")
            
            # Try to clear OTP chat history
            clear_result = await clear_otp_messages(session)
            
            if clear_result['success']:
                await status_msg.edit(
                    f"✅ **PESAN OTP UDAH DIBERSIHIN**\n\n"
                    f"📱 **Untuk:** `{session.get('phone', 'Tidak diketahui')}`\n"
                    f"📊 **Jumlah Chat OTP Dihapus:** `{clear_result.get('count', 'Tidak diketahui')}`",
                    buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
                )
            else:
                await status_msg.edit(
                    f"❌ **GAGAL HAPUS PESAN OTP**\n\n"
                    f"Pesan: {clear_result['error']}",
                    buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")]
                )
        else:
            await event.answer("Session nggak ketemu.")
    except Exception as e:
        print(f"Error in clear_otp_chat_history: {e}")
        try:
            await event.answer(f"Ada error nih waktu hapus pesan OTP")
            await event.respond(f"Error: {str(e)}", buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")])
        except:
            pass

async def clear_otp_messages(session):
    """Clear OTP messages from Telegram service accounts."""
    client = None
    session_path = f"temp_session_{session.get('user_id', 'unknown')}_{int(time.time())}.session"
    
    result = {'success': False, 'error': 'Error tidak diketahui', 'count': 0}
    
    try:
        # Try to create a client with the saved session data
        if not session.get('session_data'):
            return {'success': False, 'error': "Data session gak ada"}
            
        # Write session data to file
        with open(session_path, 'wb') as f:
            f.write(bytes.fromhex(session['session_data']))
        
        # Add a small delay to avoid connection errors
        await asyncio.sleep(1)
        
        # Connect to Telegram with better error handling
        client = TelegramClient(
            session_path.replace('.session', ''), 
            API_ID, 
            API_HASH, 
            connection_retries=5,
            retry_delay=2
        )
        
        # Connect with longer timeout
        try:
            await asyncio.wait_for(client.connect(), timeout=20)
        except asyncio.TimeoutError:
            return {'success': False, 'error': "Koneksi timeout"}
        
        # Wait after connection
        await asyncio.sleep(2)
        
        # Ensure we're connected and authorized
        if not await client.is_user_authorized():
            print(f"Session {session.get('phone')} tidak terotorisasi saat mencoba clear OTP chats")
            # Try once more with forced reconnection
            await client.disconnect()
            await asyncio.sleep(2)
            await client.connect()
            await asyncio.sleep(1)
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': "Session gak valid, coba lagi nanti"}
        
        # Get dialogs and delete OTP senders only
        cleared_count = 0
        found_count = 0
        
        try:
            # Try to delete chats with known OTP senders
            for otp_sender in OTP_SENDERS:
                try:
                    entity = await client.get_entity(otp_sender)
                    found_count += 1
                    
                    # Delete chat history with this OTP sender
                    await client(DeleteHistoryRequest(
                        peer=entity,
                        max_id=0,
                        just_clear=True,
                        revoke=False
                    ))
                    
                    cleared_count += 1
                    print(f"Berhasil menghapus pesan dari {otp_sender}")
                    
                    # Add a small delay between deletions
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"Error clearing chat with {otp_sender}: {e}")
                    continue
            
            # Also look for chats that match OTP sender patterns
            async for dialog in client.iter_dialogs(limit=20):
                try:
                    dialog_title = dialog.name or ""
                    dialog_entity_type = str(type(dialog.entity))
                    
                    # Check if this might be an OTP service
                    is_service_account = False
                    
                    # Check for common OTP sender patterns in names
                    otp_keywords = ['telegram', 'code', 'otp', 'verification', 'login', 'service']
                    if (any(keyword in dialog_title.lower() for keyword in otp_keywords) or 
                        "User" in dialog_entity_type and dialog.entity.bot):
                        is_service_account = True
                    
                    # Check phone-like names
                    if not is_service_account and (
                            dialog_title.startswith('+') or 
                            dialog_title.isdigit() or 
                            (dialog_title.startswith('telegram') and dialog_title[-1].isdigit())
                        ):
                        is_service_account = True
                    
                    if is_service_account:
                        found_count += 1
                        # Delete chat history with this service account
                        await client(DeleteHistoryRequest(
                            peer=dialog.entity,
                            max_id=0,
                            just_clear=True,
                            revoke=False
                        ))
                        
                        cleared_count += 1
                        print(f"Berhasil menghapus pesan dari {dialog_title} (service account)")
                        
                        # Add a small delay between deletions
                        await asyncio.sleep(1)
                except Exception as dialog_error:
                    print(f"Error clearing possible service dialog {dialog.name}: {dialog_error}")
                    continue
        except Exception as e:
            print(f"Error iterating dialogs for OTP clear: {e}")
            return {'success': False, 'error': f"Error saat cari dialog OTP: {str(e)}"}
        
        if cleared_count > 0:
            return {'success': True, 'count': cleared_count, 'found': found_count}
        elif found_count > 0:
            return {'success': False, 'error': f"Ketemu {found_count} dialog OTP tapi gagal hapus"}
        else:
            return {'success': False, 'error': f"Gak ada dialog OTP buat dihapus"}
    
    except FloodWaitError as e:
        print(f"FloodWaitError: {e}")
        return {'success': False, 'error': f"Telegram minta nunggu {e.seconds} detik"}
    except Exception as e:
        print(f"Error in clear_otp_messages: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        # Ensure client is disconnected
        if client:
            try:
                await client.disconnect()
            except:
                pass
        
        # Clean up session file
        try:
            await asyncio.sleep(1)  # Small delay before cleanup
            if os.path.exists(session_path):
                os.remove(session_path)
            if os.path.exists(session_path.replace('.session', '') + '.session'):
                os.remove(session_path.replace('.session', '') + '.session')
        except Exception as e:
            print(f"Error cleaning up session files: {e}")

async def clear_chat_messages(session):
    """Clear chat messages for the session."""
    client = None
    session_path = f"temp_session_{session.get('user_id', 'unknown')}_{int(time.time())}.session"
    
    result = {'success': False, 'error': 'Error tidak diketahui', 'count': 0}
    
    try:
        # Try to create a client with the saved session data
        if not session.get('session_data'):
            return {'success': False, 'error': "Data session gak ada"}
            
        # Write session data to file
        with open(session_path, 'wb') as f:
            f.write(bytes.fromhex(session['session_data']))
        
        # Add a small delay to avoid connection errors
        await asyncio.sleep(1)
        
        # Connect to Telegram with better error handling
        client = TelegramClient(
            session_path.replace('.session', ''), 
            API_ID, 
            API_HASH, 
            connection_retries=5,
            retry_delay=2
        )
        
        # Connect with longer timeout
        try:
            await asyncio.wait_for(client.connect(), timeout=20)
        except asyncio.TimeoutError:
            return {'success': False, 'error': "Koneksi timeout"}
        
        # Wait after connection
        await asyncio.sleep(2)
        
        # Ensure we're connected and authorized
        if not await client.is_user_authorized():
            print(f"Session {session.get('phone')} tidak terotorisasi saat mencoba clear chat")
            # Try once more with forced reconnection
            await client.disconnect()
            await asyncio.sleep(2)
            await client.connect()
            await asyncio.sleep(1)
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': "Session gak valid, coba lagi nanti"}
        
        # Get dialogs
        dialogs_count = 0
        cleared_count = 0
        
        try:
            async for dialog in client.iter_dialogs(limit=15):
                try:
                    dialogs_count += 1
                    # Delete chat history for this dialog
                    await client(DeleteHistoryRequest(
                        peer=dialog.entity,
                        max_id=0,
                        just_clear=True,
                        revoke=False
                    ))
                    cleared_count += 1
                    # Add a small delay between deletions to avoid flood wait
                    await asyncio.sleep(0.5)
                except Exception as dialog_error:
                    print(f"Error clearing dialog {dialog.name}: {dialog_error}")
                    continue
        except Exception as dialogs_error:
            print(f"Error iterating dialogs: {dialogs_error}")
            return {'success': False, 'error': f"Error saat ambil dialog: {str(dialogs_error)}"}
        
        if cleared_count > 0:
            return {'success': True, 'count': cleared_count}
        else:
            return {'success': False, 'error': f"Gagal hapus chat (dialogs: {dialogs_count})"}
    
    except FloodWaitError as e:
        print(f"FloodWaitError: {e}")
        return {'success': False, 'error': f"Telegram minta nunggu {e.seconds} detik"}
    except Exception as e:
        print(f"Error in clear_chat_messages: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        # Ensure client is disconnected
        if client:
            try:
                await client.disconnect()
            except:
                pass
        
        # Clean up session file
        try:
            await asyncio.sleep(1)  # Small delay before cleanup
            if os.path.exists(session_path):
                os.remove(session_path)
            if os.path.exists(session_path.replace('.session', '') + '.session'):
                os.remove(session_path.replace('.session', '') + '.session')
        except Exception as e:
            print(f"Error cleaning up session files: {e}")

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"delete_")))
async def confirm_delete_session(event):
    """Confirm deletion of a session."""
    try:
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
                f"Yakin mau hapus session ini?\n\n"
                f"📱 **Nomor:** `{session.get('phone', 'Tidak diketahui')}`\n"
                f"👤 **Nama:** `{session.get('first_name', 'Tidak diketahui')}`\n"
                f"🔖 **Username:** `@{session.get('username', 'tidak ada') or 'tidak ada'}`\n",
                buttons=buttons
            )
        else:
            await event.answer("Session nggak ketemu.")
    except Exception as e:
        print(f"Error in confirm_delete_session: {e}")
        await event.answer(f"Waduh error nih: {str(e)}")

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"confirm_delete_")))
async def delete_session(event):
    """Delete a session after confirmation."""
    try:
        user_id = event.sender_id
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
            return
        
        # Get selected session index
        session_idx = int(event.data.decode().split("_")[2])
        user_id_str = str(user_id)
        current_page = user_current_page.get(user_id_str, 0)
        
        if user_id_str in active_sessions and 0 <= session_idx < len(active_sessions[user_id_str]):
            # Get session info before removing
            session = active_sessions[user_id_str][session_idx]
            
            # Remove the session
            del active_sessions[user_id_str][session_idx]
            
            # Save updated sessions
            save_sessions()
            
            await event.edit(
                f"✅ **SESSION UDAH DIHAPUS**\n\n"
                f"Session buat `{session.get('phone', 'Tidak diketahui')}` (`{session.get('first_name', 'Tidak diketahui')}`) udah dihapus.",
                buttons=[Button.inline("⬅️ Balik ke Daftar", f"back_to_list_{current_page}")]
            )
        else:
            await event.answer("Session nggak ketemu.")
    except Exception as e:
        print(f"Error in delete_session: {e}")
        await event.answer(f"Waduh error nih: {str(e)}")

async def get_latest_otp(session):
    """Get the latest OTP message from the session."""
    client = None
    session_path = f"temp_session_{session.get('user_id', 'unknown')}_{int(time.time())}.session"
    
    result = {'success': False, 'error': 'Error tidak diketahui'}
    
    try:
        # Try to create a client with the saved session data
        if not session.get('session_data'):
            return {'success': False, 'error': "Data session gak ada"}
            
        # Write session data to file - ensure it has .session extension
        with open(session_path, 'wb') as f:
            f.write(bytes.fromhex(session['session_data']))
        
        # Add a small delay to avoid connection errors
        await asyncio.sleep(1)
        
        # Connect to Telegram with better error handling and more retries
        client = TelegramClient(
            session_path.replace('.session', ''),  # TelegramClient adds .session itself
            API_ID, 
            API_HASH, 
            connection_retries=5,
            retry_delay=2
        )
        
        # Use a longer timeout for connection
        try:
            await asyncio.wait_for(client.connect(), timeout=20)
        except asyncio.TimeoutError:
            return {'success': False, 'error': "Koneksi timeout"}
        
        # Wait a bit after connection before checking authorization
        await asyncio.sleep(2)
        
        # Ensure we're connected and authorized
        if not await client.is_user_authorized():
            print(f"Session {session.get('phone')} tidak terotorisasi saat mencoba get OTP")
            # Try once more with forced reconnection
            await client.disconnect()
            await asyncio.sleep(2)
            await client.connect()
            await asyncio.sleep(1)
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': "Session gak valid, coba lagi nanti"}
            
        # Add a small delay before message retrieval
        await asyncio.sleep(2)
        
        try:
            # Try both OTP sender and Telegram service account with better handling
            sender_entities = OTP_SENDERS
            
            for sender in sender_entities:
                try:
                    print(f"Mencoba mendapatkan pesan dari {sender}")
                    # Get messages from this sender
                    messages = []
                    try:
                        async for message in client.iter_messages(sender, limit=15):
                            if message and message.message:
                                messages.append(message)
                    except Exception as iter_error:
                        print(f"Error iterating messages from {sender}: {iter_error}")
                        continue
                    
                    # Look for OTP in messages
                    if messages:
                        print(f"Ditemukan {len(messages)} pesan dari {sender}")
                        for msg in messages:
                            if not msg.message:
                                continue
                                
                            # Extract OTP (usually a 5-6 digit number)
                            import re
                            otp_match = re.search(r'\b\d{4,6}\b', msg.message)
                                
                            if otp_match:
                                otp_code = otp_match.group(0)
                                return {
                                    'success': True,
                                    'otp': otp_code,
                                    'time': msg.date.strftime('%Y-%m-%d %H:%M:%S'),
                                    'source': sender
                                }
                    else:
                        print(f"Tidak ada pesan dari {sender}")
                except Exception as msg_error:
                    print(f"Error retrieving messages from {sender}: {msg_error}")
                    continue
            
            # If we get here, no OTP was found, try getting recent messages from any source
            try:
                print("Mencari pesan OTP dari pesan terbaru")
                recent_messages = []
                async for dialog in client.iter_dialogs(limit=5):
                    try:
                        async for message in client.iter_messages(dialog.entity, limit=5):
                            if message and message.message:
                                recent_messages.append((dialog.name, message))
                    except:
                        continue
                
                # Check all recent messages for OTP patterns
                for dialog_name, msg in recent_messages:
                    if not msg.message:
                        continue
                        
                    # Look for OTP patterns in message
                    import re
                    otp_match = re.search(r'\b\d{4,6}\b', msg.message)
                    
                    # Also look for typical OTP message patterns
                    otp_keywords = ['code', 'otp', 'verification', 'login', 'kode', 'verifikasi']
                    has_otp_keywords = any(keyword in msg.message.lower() for keyword in otp_keywords)
                    
                    if otp_match and has_otp_keywords:
                        otp_code = otp_match.group(0)
                        return {
                            'success': True,
                            'otp': otp_code,
                            'time': msg.date.strftime('%Y-%m-%d %H:%M:%S'),
                            'source': dialog_name
                        }
            except Exception as recent_error:
                print(f"Error checking recent messages: {recent_error}")
            
            # If we get here, no OTP was found
            return {'success': False, 'error': "Gak ketemu pesan OTP nih, coba lagi nanti"}
            
        except Exception as e:
            print(f"Error in message retrieval: {e}")
            return {'success': False, 'error': f"Error saat cari pesan: {str(e)}"}
    
    except FloodWaitError as e:
        print(f"FloodWaitError: {e}")
        return {'success': False, 'error': f"Telegram minta nunggu {e.seconds} detik"}
    except PhoneNumberBannedError:
        return {'success': False, 'error': "Nomor udah dibanned!"}
    except AuthKeyError:
        return {'success': False, 'error': "Session key gak valid"}
    except Exception as e:
        print(f"Error in get_latest_otp: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        # Ensure client is disconnected
        if client:
            try:
                await client.disconnect()
            except:
                pass
        
        # Clean up session file
        try:
            await asyncio.sleep(1)  # Small delay before cleanup
            if os.path.exists(session_path):
                os.remove(session_path)
            if os.path.exists(session_path.replace('.session', '') + '.session'):
                os.remove(session_path.replace('.session', '') + '.session')
        except Exception as e:
            print(f"Error cleaning up session files: {e}")

# Add the new invite contact functionality
@events.register(events.CallbackQuery(data=b"invite_contacts"))
async def invite_contacts_setup(event):
    """Setup for inviting contacts to a group."""
    try:
        user_id = event.sender_id
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.answer("Sori bro, cuma admin yang bisa pake fitur ini.")
            return
        
        # Ask for the group link
        await event.edit(
            "🔗 **MAU INVITE KONTAK KE GRUP NIH**\n\n"
            "Cus, kirim link grup yang mau lu tambahin kontak.\n"
            "Format: `https://t.me/+abc123` atau `@namegrup`",
            buttons=[Button.inline("❌ Gajadi", f"back_to_list_0")]
        )
        
        # Store that we're expecting a group link
        user_id_str = str(user_id)
        if 'pending_actions' not in globals():
            globals()['pending_actions'] = {}
        
        globals()['pending_actions'][user_id_str] = {
            'action': 'waiting_for_group_link',
            'data': {}
        }
    except Exception as e:
        print(f"Error in invite_contacts_setup: {e}")
        await event.answer(f"Waduh error nih: {str(e)}")

@events.register(events.NewMessage(func=lambda e: e.is_private))
async def handle_invite_setup_messages(event):
    """Handle messages for invite setup process."""
    try:
        user_id = event.sender_id
        user_id_str = str(user_id)
        
        # Only allow admin
        if user_id != ADMIN_ID:
            return
        
        # Check if we're expecting a message from this user
        if 'pending_actions' not in globals() or user_id_str not in globals()['pending_actions']:
            # This is just a regular message, let the handle_message function handle it
            return
        
        pending_action = globals()['pending_actions'][user_id_str]
        
        # Handle the different stages of setup
        if pending_action['action'] == 'waiting_for_group_link':
            # Get the group link
            group_link = event.text.strip()
            
            # Store the group link
            pending_action['data']['group_link'] = group_link
            pending_action['action'] = 'waiting_for_target_count'
            
            # Ask for target count
            await event.respond(
                "🎯 **MAU INVITE BERAPA NIH BOS?**\n\n"
                f"Link grup: `{group_link}`\n\n"
                "Mau invite berapa banyak kontak? Ketik angkanya aja (misal: 50)",
                buttons=[Button.inline("❌ Gajadi", f"back_to_list_0")]
            )
            
            # Delete the user's message containing the group link for cleanliness
            await event.delete()
            
        elif pending_action['action'] == 'waiting_for_target_count':
            # Try to get target count
            try:
                target_count = int(event.text.strip())
                if target_count <= 0:
                    await event.respond(
                        "❌ Masa targetnya 0 sih? Isi yang bener dong.",
                        buttons=[Button.inline("❌ Gajadi", f"back_to_list_0")]
                    )
                    return
            except ValueError:
                await event.respond(
                    "❌ Format gak valid. Masukkin angka dong, jangan aneh-aneh.",
                    buttons=[Button.inline("❌ Gajadi", f"back_to_list_0")]
                )
                return
            
            # Store the target count and prepare data
            group_link = pending_action['data']['group_link']
            
            # Clear the pending action
            del globals()['pending_actions'][user_id_str]
            
            # Delete the user's message containing the target count for cleanliness
            await event.delete()
            
            # Confirm and start the invite process
            confirmation_msg = await event.respond(
                "✅ **KONFIRMASI INVITE KONTAK**\n\n"
                f"📱 Link grup: `{group_link}`\n"
                f"🎯 Target invite: `{target_count}`\n\n"
                "Siap gaskeun nih?",
                buttons=[
                    [
                        Button.inline("✅ Gas!", f"start_invite_{group_link}_{target_count}"),
                        Button.inline("❌ Gajadi", f"back_to_list_0")
                    ]
                ]
            )
    except Exception as e:
        print(f"Error in handle_invite_setup_messages: {e}")
        if 'pending_actions' in globals() and user_id_str in globals()['pending_actions']:
            del globals()['pending_actions'][user_id_str]
        await event.respond(f"❌ Waduh error: {str(e)}", buttons=[Button.inline("⬅️ Balik", f"back_to_list_0")])

@events.register(events.CallbackQuery(data=lambda x: x.startswith(b"start_invite_")))
async def start_invite_process(event):
    """Start the process of inviting contacts to a group."""
    try:
        user_id = event.sender_id
        user_id_str = str(user_id)
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.answer("Sori bro, cuma admin yang bisa pake fitur ini.")
            return
        
        # Parse the data from the callback
        data = event.data.decode().split("_")
        group_link = data[2]
        target_count = int(data[3])
        
        # Show the processing message
        status_msg = await event.edit(
            "⏳ **MULAI PROSES INVITE KONTAK**\n\n"
            f"🔗 Link grup: `{group_link}`\n"
            f"🎯 Target invite: `{target_count}`\n\n"
            "Siap-siap akun buat invite..."
        )
        
        # Start the invite process
        create_task(process_invite_contacts(user_id, group_link, target_count, status_msg))
        
    except Exception as e:
        print(f"Error in start_invite_process: {e}")
        await event.answer(f"Waduh error nih: {str(e)}")
        await event.edit(f"❌ Waduh error: {str(e)}", buttons=[Button.inline("⬅️ Balik", f"back_to_list_0")])

async def process_invite_contacts(user_id, group_link, target_count, status_msg):
    """Process inviting contacts to a group using multiple accounts."""
    user_id_str = str(user_id)
    
    # Keep track of results
    total_invited = 0
    results_per_account = []
    
    try:
        # Check if we have sessions
        if user_id_str not in active_sessions or not active_sessions[user_id_str]:
            await status_msg.edit(
                "❌ **GAK ADA SESSION AKTIF**\n\n"
                "Gak ada session buat dipakai nih. Upload session dulu gih.",
                buttons=[Button.inline("⬅️ Balik", f"back_to_list_0")]
            )
            return
        
        # Get the list of sessions
        sessions = active_sessions[user_id_str]
        
        # Update status message
        await status_msg.edit(
            "⏳ **PROSES INVITE KONTAK DIMULAI**\n\n"
            f"🔗 Link grup: `{group_link}`\n"
            f"🎯 Target invite: `{target_count}`\n"
            f"📱 Total akun: `{len(sessions)}`\n\n"
            "Status: Nyiapin sesi telegram..."
        )
        
        # Process each session until we reach the target
        for session_idx, session in enumerate(sessions):
            if total_invited >= target_count:
                break
                
            # Update status message for this account
            await status_msg.edit(
                f"⏳ **PROSES INVITE KONTAK ({total_invited}/{target_count})**\n\n"
                f"🔗 Link grup: `{group_link}`\n"
                f"📱 Pake akun: `{session.get('phone', 'Tidak diketahui')}` ({session_idx+1}/{len(sessions)})\n"
                f"👤 Nama: `{session.get('first_name', 'Tidak diketahui')}`\n\n"
                "Status: Konek ke Telegram..."
            )
            
            # Use this session to invite contacts
            invited_with_this_account = 0
            
            # Create a client for this session
            client = None
            session_path = f"temp_session_{session.get('user_id', 'unknown')}_{int(time.time())}.session"
            
            try:
                # Write session data to file
                if not session.get('session_data'):
                    results_per_account.append({
                        'phone': session.get('phone', 'Tidak diketahui'),
                        'name': session.get('first_name', 'Tidak diketahui'),
                        'invited': 0,
                        'status': "Data session gak ada"
                    })
                    continue
                    
                with open(session_path, 'wb') as f:
                    f.write(bytes.fromhex(session['session_data']))
                
                # Connect to Telegram
                client = TelegramClient(
                    session_path.replace('.session', ''), 
                    API_ID, 
                    API_HASH, 
                    connection_retries=5,
                    retry_delay=2
                )
                
                # Connect with timeout
                try:
                    await asyncio.wait_for(client.connect(), timeout=20)
                except asyncio.TimeoutError:
                    results_per_account.append({
                        'phone': session.get('phone', 'Tidak diketahui'),
                        'name': session.get('first_name', 'Tidak diketahui'),
                        'invited': 0,
                        'status': "Koneksi timeout"
                    })
                    continue
                
                # Wait after connection
                await asyncio.sleep(2)
                
                # Ensure we're connected and authorized
                if not await client.is_user_authorized():
                    print(f"Session {session.get('phone')} tidak terotorisasi")
                    # Try once more with forced reconnection
                    await client.disconnect()
                    await asyncio.sleep(2)
                    await client.connect()
                    await asyncio.sleep(1)
                    
                    if not await client.is_user_authorized():
                        results_per_account.append({
                            'phone': session.get('phone', 'Tidak diketahui'),
                            'name': session.get('first_name', 'Tidak diketahui'),
                            'invited': 0,
                            'status': "Session gak valid"
                        })
                        continue
                
                # Update status
                await status_msg.edit(
                    f"⏳ **PROSES INVITE KONTAK ({total_invited}/{target_count})**\n\n"
                    f"🔗 Link grup: `{group_link}`\n"
                    f"📱 Pake akun: `{session.get('phone', 'Tidak diketahui')}` ({session_idx+1}/{len(sessions)})\n"
                    f"👤 Nama: `{session.get('first_name', 'Tidak diketahui')}`\n\n"
                    "Status: Lagi join grup..."
                )
                
                # Try to join the group first
                group_entity = None
                try:
                    # Check if it's a private group link
                    if group_link.startswith('https://t.me/+') or group_link.startswith('https://t.me/joinchat/'):
                        invite_hash = group_link.split('/')[-1]
                        if invite_hash.startswith('+'):
                            invite_hash = invite_hash[1:]
                        
                        try:
                            # Try to join the group
                            await client(functions.messages.ImportChatInviteRequest(invite_hash))
                            await asyncio.sleep(2)
                            
                            # Find the group we just joined
                            async for dialog in client.iter_dialogs(limit=10):
                                if dialog.is_group or dialog.is_channel:
                                    group_entity = dialog.entity
                                    break
                        except errors.UserAlreadyParticipantError:
                            # Already in the group, try to find it
                            async for dialog in client.iter_dialogs(limit=20):
                                if dialog.is_group or dialog.is_channel:
                                    group_entity = dialog.entity
                                    break
                        except Exception as e:
                            print(f"Error joining group with invite link: {e}")
                            if "FLOOD_WAIT" in str(e):
                                flood_time = int(str(e).split('of ')[1].split(' seconds')[0])
                                results_per_account.append({
                                    'phone': session.get('phone', 'Tidak diketahui'),
                                    'name': session.get('first_name', 'Tidak diketahui'),
                                    'invited': 0,
                                    'status': f"Rate limit pas join grup (tunggu {flood_time} detik)"
                                })
                                continue
                            else:
                                results_per_account.append({
                                    'phone': session.get('phone', 'Tidak diketahui'),
                                    'name': session.get('first_name', 'Tidak diketahui'),
                                    'invited': 0,
                                    'status': f"Error join grup: {str(e)}"
                                })
                                continue
                    else:
                        # It's a public group
                        group_username = group_link.replace('https://t.me/', '').replace('@', '')
                        try:
                            # Try to join the group
                            group_entity = await client.get_entity(group_username)
                            
                            # If it's a channel or supergroup, we need to join
                            if hasattr(group_entity, 'broadcast') and group_entity.broadcast:
                                try:
                                    await client(functions.channels.JoinChannelRequest(group_entity))
                                    await asyncio.sleep(2)
                                except errors.UserAlreadyParticipantError:
                                    # Already in the channel
                                    pass
                        except Exception as e:
                            print(f"Error joining public group: {e}")
                            results_per_account.append({
                                'phone': session.get('phone', 'Tidak diketahui'),
                                'name': session.get('first_name', 'Tidak diketahui'),
                                'invited': 0,
                                'status': f"Error join grup publik: {str(e)}"
                            })
                            continue
                
                    if not group_entity:
                        results_per_account.append({
                            'phone': session.get('phone', 'Tidak diketahui'),
                            'name': session.get('first_name', 'Tidak diketahui'),
                            'invited': 0,
                            'status': "Gak ketemu grupnya"
                        })
                        continue
                    
                    # Update status
                    await status_msg.edit(
                        f"⏳ **PROSES INVITE KONTAK ({total_invited}/{target_count})**\n\n"
                        f"🔗 Link grup: `{group_link}`\n"
                        f"📱 Pake akun: `{session.get('phone', 'Tidak diketahui')}` ({session_idx+1}/{len(sessions)})\n"
                        f"👤 Nama: `{session.get('first_name', 'Tidak diketahui')}`\n\n"
                        "Status: Ambil kontak mutual..."
                    )
                    
                    # Get mutual contacts
                    contacts = []
                    try:
                        # Use GetContactsRequest instead of iter_contacts
                        from telethon.tl.functions.contacts import GetContactsRequest
                        result = await client(GetContactsRequest(hash=0))
                        
                        # Filter for mutual contacts
                        for user in result.users:
                            if hasattr(user, 'mutual_contact') and user.mutual_contact:
                                contacts.append(user)
                        
                        print(f"Found {len(contacts)} mutual contacts")
                    except Exception as contact_error:
                        print(f"Error getting mutual contacts: {contact_error}")
                        results_per_account.append({
                            'phone': session.get('phone', 'Tidak diketahui'),
                            'name': session.get('first_name', 'Tidak diketahui'),
                            'invited': 0,
                            'status': f"Error ambil kontak: {str(contact_error)}"
                        })
                        continue
                    
                    # Update status
                    await status_msg.edit(
                        f"⏳ **PROSES INVITE KONTAK ({total_invited}/{target_count})**\n\n"
                        f"🔗 Link grup: `{group_link}`\n"
                        f"📱 Pake akun: `{session.get('phone', 'Tidak diketahui')}` ({session_idx+1}/{len(sessions)})\n"
                        f"👤 Nama: `{session.get('first_name', 'Tidak diketahui')}`\n"
                        f"📊 Kontak mutual: `{len(contacts)}`\n\n"
                        "Status: Mulai invite kontak..."
                    )
                    
                    # Start inviting contacts
                    for i, contact in enumerate(contacts):
                        # Check if we've reached our target
                        if total_invited >= target_count:
                            break
                            
                        # Update status periodically
                        if i % 5 == 0 or i == len(contacts) - 1:
                            await status_msg.edit(
                                f"⏳ **PROSES INVITE KONTAK ({total_invited}/{target_count})**\n\n"
                                f"🔗 Link grup: `{group_link}`\n"
                                f"📱 Pake akun: `{session.get('phone', 'Tidak diketahui')}` ({session_idx+1}/{len(sessions)})\n"
                                f"👤 Nama: `{session.get('first_name', 'Tidak diketahui')}`\n"
                                f"📊 Progress: `{i+1}/{len(contacts)}` kontak\n"
                                f"✅ Invited: `{invited_with_this_account}` kontak\n\n"
                                f"Status: Invite {contact.first_name}..."
                            )
                        
                        try:
                            # Try to add the contact to the group
                            await client(functions.channels.InviteToChannelRequest(
                                channel=group_entity,
                                users=[contact]
                            ))
                            
                            # Successfully invited
                            invited_with_this_account += 1
                            total_invited += 1
                            
                            # Small delay to avoid flood wait
                            await asyncio.sleep(1 + random.random() * 2)
                        except errors.FloodWaitError as flood_error:
                            # Hit rate limit, move to next account
                            flood_time = flood_error.seconds
                            results_per_account.append({
                                'phone': session.get('phone', 'Tidak diketahui'),
                                'name': session.get('first_name', 'Tidak diketahui'),
                                'invited': invited_with_this_account,
                                'status': f"Rate limit (tunggu {flood_time} detik)"
                            })
                            break
                        except Exception as invite_error:
                            # Other error, continue with next contact
                            print(f"Error inviting {contact.first_name}: {invite_error}")
                            continue
                    
                    # Add the results for this account
                    if invited_with_this_account > 0 or not results_per_account:
                        results_per_account.append({
                            'phone': session.get('phone', 'Tidak diketahui'),
                            'name': session.get('first_name', 'Tidak diketahui'),
                            'invited': invited_with_this_account,
                            'status': "Selesai" if invited_with_this_account > 0 else "Gak ada kontak yang diinvite"
                        })
                    
                except Exception as e:
                    print(f"Error in group join process: {e}")
                    traceback.print_exc()
                    results_per_account.append({
                        'phone': session.get('phone', 'Tidak diketahui'),
                        'name': session.get('first_name', 'Tidak diketahui'),
                        'invited': invited_with_this_account,
                        'status': f"Error: {str(e)}"
                    })
            except Exception as session_error:
                print(f"Error with session {session.get('phone')}: {session_error}")
                traceback.print_exc()
                results_per_account.append({
                    'phone': session.get('phone', 'Tidak diketahui'),
                    'name': session.get('first_name', 'Tidak diketahui'),
                    'invited': 0,
                    'status': f"Error session: {str(session_error)}"
                })
            finally:
                # Disconnect the client
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
                
                # Clean up session file
                try:
                    await asyncio.sleep(1)  # Small delay before cleanup
                    if os.path.exists(session_path):
                        os.remove(session_path)
                    if os.path.exists(session_path.replace('.session', '') + '.session'):
                        os.remove(session_path.replace('.session', '') + '.session')
                except Exception as e:
                    print(f"Error cleaning up session files: {e}")
        
        # Process complete, show final results
        results_text = "📊 **HASIL INVITE PER AKUN:**\n\n"
        for i, result in enumerate(results_per_account):
            results_text += f"{i+1}. `{result['phone']}` ({result['name']})\n"
            results_text += f"   ✅ Invited: `{result['invited']}` kontak\n"
            results_text += f"   📝 Status: `{result['status']}`\n\n"
        
        await status_msg.edit(
            f"✅ **INVITE KONTAK SELESAI CUY**\n\n"
            f"🔗 Link grup: `{group_link}`\n"
            f"🎯 Target: `{target_count}`\n"
            f"👥 Total invited: `{total_invited}`\n"
            f"📱 Akun dipake: `{len(results_per_account)}`\n\n"
            f"{results_text}",
            buttons=[Button.inline("⬅️ Balik ke Daftar", f"back_to_list_0")]
        )
        
    except Exception as e:
        print(f"Error in process_invite_contacts: {e}")
        traceback.print_exc()
        
        # Show error with any results we got
        results_text = ""
        if results_per_account:
            results_text = "📊 **HASIL INVITE PER AKUN:**\n\n"
            for i, result in enumerate(results_per_account):
                results_text += f"{i+1}. `{result['phone']}` ({result['name']})\n"
                results_text += f"   ✅ Invited: `{result['invited']}` kontak\n"
                results_text += f"   📝 Status: `{result['status']}`\n\n"
        
        await status_msg.edit(
            f"❌ **ERROR COY DALAM PROSES INVITE**\n\n"
            f"Error: {str(e)}\n\n"
            f"🔗 Link grup: `{group_link}`\n"
            f"🎯 Target: `{target_count}`\n"
            f"👥 Total invited: `{total_invited}`\n"
            f"{results_text}",
            buttons=[Button.inline("⬅️ Balik ke Daftar", f"back_to_list_0")]
        )

@events.register(events.NewMessage(func=lambda e: e.is_private))
async def handle_message(event):
    """Handle incoming messages in private chats."""
    try:
        user_id = event.sender_id
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.respond("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
            return
        
        # Check if the message is being handled by handle_invite_setup_messages
        user_id_str = str(user_id)
        if 'pending_actions' in globals() and user_id_str in globals()['pending_actions']:
            # Let handle_invite_setup_messages handle this
            return
        
        # Check if the message contains a document (file)
        if event.document:
            # Get file name and mime type
            file_name = event.file.name if hasattr(event.file, 'name') else f"unknown_file_{int(time.time())}"
            mime_type = event.file.mime_type if hasattr(event.file, 'mime_type') else ""
            
            # Check if it's a zip file
            if file_name.lower().endswith('.zip') or mime_type == 'application/zip':
                # Download the zip file
                download_path = f"temp_zip_{int(time.time())}.zip"
                await event.respond(f"⏬ Lagi download file ZIP: `{file_name}`...")
                
                # Download with a small delay to prevent errors
                await asyncio.sleep(0.5)
                await event.download_media(file=download_path)
                
                # Process the zip file
                create_task(process_zip_file(download_path, user_id, event.id))
            else:
                # Download the file (regular session file)
                download_path = f"temp_{int(time.time())}_{file_name}"
                
                # Send a processing message
                processing_msg = await event.respond(f"⏬ Lagi download file session: `{file_name}`...")
                
                # Download with a small delay to prevent errors
                await asyncio.sleep(0.5)
                await event.download_media(file=download_path)
                
                # Check the session immediately
                await process_single_session(download_path, user_id, event.id, processing_msg)
    except Exception as e:
        print(f"Error in handle_message: {e}")
        await event.respond(f"❌ Error pas proses file: {str(e)}")

async def process_single_session(file_path, user_id, message_id, processing_msg=None):
    """Process a single session file."""
    try:
        if processing_msg:
            await processing_msg.edit("⏳ Lagi proses file session...")
        else:
            processing_msg = await bot.send_message(user_id, "⏳ Lagi proses file session...", reply_to=message_id)
        
        # Add a small delay to prevent errors
        await asyncio.sleep(1)
        
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
                except Exception as e:
                    print(f"Error reading session data: {e}")
                
                # Add to active sessions
                active_sessions[user_id_str].append({
                    'user_id': result.get('user_id'),
                    'first_name': result.get('first_name', 'Tidak diketahui'),
                    'last_name': result.get('last_name', 'Tidak ada'),
                    'username': result.get('username'),
                    'phone': result.get('phone', 'Tidak diketahui'),
                    'creation_date': creation_date,
                    'is_premium': result.get('is_premium', 'Tidak diketahui'),
                    'has_2fa': result.get('has_2fa'),  # Store actual boolean for 2FA
                    'session_data': session_data,
                    'last_status': 'Baru Diimpor'
                })
                
                # Save sessions
                save_sessions()
            
            message = (
                f"✅ **SESSION VALID BRO**\n\n"
                f"📱 **Nomor:** `{result.get('phone', 'Tidak diketahui')}`\n"
                f"👤 **Nama Depan:** `{result.get('first_name', 'Tidak diketahui')}`\n"
                f"👤 **Nama Belakang:** `{result.get('last_name', 'Tidak ada')}`\n"
                f"🔖 **Username:** `{result.get('username', 'Tidak ada')}`\n"
                f"🆔 **User ID:** `{result.get('user_id', 'Tidak diketahui')}`\n"
                f"📅 **Tanggal Pembuatan:** `{creation_date}`\n"
                f"🔐 **Premium:** `{result.get('is_premium', 'Tidak diketahui')}`\n"
                f"🔄 **2FA/Password:** `{'Ya' if result.get('has_2fa') == True else 'Tidak'}`\n"
                f"🔑 **Password Hint:** `{result.get('password_hint', 'Tidak ada')}`\n"
            )
        else:
            message = f"❌ **SESSION GA VALID CUY**\n\nError: {result.get('error', 'Error tidak diketahui')}"
        
        # Edit the processing message with the results
        await processing_msg.edit(message)
        
        # Clean up the session file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error removing file {file_path}: {e}")
    except Exception as e:
        print(f"Error in process_single_session: {e}")
        if processing_msg:
            await processing_msg.edit(f"❌ Error pas proses session: {str(e)}")

async def process_zip_file(file_path, user_id, message_id):
    """Extract and process session files from a zip archive."""
    processing_msg = None
    extract_dir = os.path.join(TEMP_DIR, f"extract_{int(time.time())}")
    
    try:
        processing_msg = await bot.send_message(
            user_id,
            "⏳ Lagi proses file ZIP...",
            reply_to=message_id
        )
        
        # Create temp directory if it doesn't exist
        ensure_temp_dirs()
        
        # Create a unique subfolder for this extraction
        os.makedirs(extract_dir, exist_ok=True)
        
        sessions_found = 0
        sessions_valid = 0
        
        # Extract the zip file
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Update processing message
            await processing_msg.edit("⏳ ZIP udah diextract, lagi cari file session...")
        except zipfile.BadZipFile:
            await processing_msg.edit("❌ File ga valid atau bukan ZIP bro.")
            return
        
        # Look for session files in the expected structure: sessions/users/
        sessions_dir = os.path.join(extract_dir, "sessions", "users")
        
        # Check if the expected directory exists
        if os.path.exists(sessions_dir) and os.path.isdir(sessions_dir):
            # Get all files in the sessions/users directory
            session_files = []
            for root, _, files in os.walk(sessions_dir):
                for file in files:
                    # Skip obvious non-session files
                    if file.endswith(('.txt', '.md', '.json', '.zip')):
                        continue
                    
                    session_files.append(os.path.join(root, file))
            
            total_files = len(session_files)
            
            if total_files > 0:
                await processing_msg.edit(f"⏳ Ketemu {total_files} file session, lagi diproses...")
                
                # Process each session file
                count = 0
                for session_file in session_files:
                    count += 1
                    if count % 3 == 0:  # Update progress every 3 files
                        await processing_msg.edit(f"⏳ Lagi proses file session {count}/{total_files}...")
                    
                    sessions_found += 1
                    
                    # Add a random delay between 1-3 seconds to prevent rate limiting
                    await asyncio.sleep(1 + random.random() * 2)
                    
                    result = await check_session_file(session_file)
                    
                    if result['valid']:
                        sessions_valid += 1
                        
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
                            except Exception as e:
                                print(f"Error reading session data: {e}")
                            
                            # Add to active sessions
                            active_sessions[user_id_str].append({
                                'user_id': result.get('user_id'),
                                'first_name': result.get('first_name', 'Tidak diketahui'),
                                'last_name': result.get('last_name', 'Tidak ada'),
                                'username': result.get('username'),
                                'phone': result.get('phone', 'Tidak diketahui'),
                                'creation_date': creation_date,
                                'is_premium': result.get('is_premium', 'Tidak diketahui'),
                                'has_2fa': result.get('has_2fa'),  # Store actual boolean
                                'session_data': session_data,
                                'password_hint': result.get('password_hint', 'Tidak ada'),
                                'last_status': 'Baru Diimpor'
                            })
                
                # Save sessions
                save_sessions()
            else:
                await processing_msg.edit("❌ Gak ketemu file session di folder sessions/users/ di ZIP-nya.")
                return
        else:
            await processing_msg.edit("❌ Folder sessions/users/ gak ada di ZIP-nya.")
            return
            
    except Exception as e:
        print(f"Error in process_zip_file: {e}")
        if processing_msg:
            await processing_msg.edit(f"❌ Error pas proses ZIP: {str(e)}")
        return
    finally:
        # Clean up
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
        except Exception as e:
            print(f"Error cleaning up files: {e}")
    
    # Final report
    if sessions_found > 0:
        if processing_msg:
            await processing_msg.edit(
                f"✅ **PROSES ZIP KELAR**\n\n"
                f"📊 **Hasil:**\n"
                f"- Session ketemu: {sessions_found}\n"
                f"- Session valid: {sessions_valid}\n\n"
                f"Pake /kelola buat lihat dan kelola session-nya."
            )
    else:
        if processing_msg:
            await processing_msg.edit("❌ Gak ada file session yang ketemu di ZIP.")

async def check_session_file(file_path):
    """Check a session file and extract information from it."""
    result = {'valid': False}
    client = None
    
    try:
        # Get a unique session path
        session_name = f"check_{int(time.time())}_{os.path.basename(file_path)}"
        session_path = session_name.replace('temp_', '')
        
        # Copy the file to the new path
        try:
            shutil.copy2(file_path, session_path)
        except Exception as e:
            print(f"Error copying session file: {e}")
            # Try to use the original path as fallback
            session_path = file_path
        
        # Save the session path
        result['session_path'] = session_path
        
        # Try to create a client with the session
        client = TelegramClient(session_path, API_ID, API_HASH, connection_retries=3)
        
        # Connect with timeout
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
        except asyncio.TimeoutError:
            result['error'] = "Koneksi timeout"
            return result
        
        # Add a small delay after connection
        await asyncio.sleep(1)
        
        # Check authorization
        if await client.is_user_authorized():
            result['valid'] = True
            
            # Add a small delay before getting user info
            await asyncio.sleep(1)
            
            try:
                # Get the current user info
                me = await client.get_me()
                
                # Basic user info
                result['user_id'] = me.id
                result['first_name'] = me.first_name
                result['last_name'] = me.last_name
                result['username'] = me.username
                result['phone'] = me.phone
                result['is_premium'] = "Ya" if getattr(me, 'premium', False) else "Tidak"
                
                # Get full user info with potentially more details
                try:
                    full_user = await client(GetFullUserRequest(me.id))
                    result['about'] = getattr(full_user.full_user, 'about', None)
                    
                    # Check for password hint
                    result['password_hint'] = getattr(full_user.full_user, 'password_hint', None)
                except:
                    # Couldn't get full user info
                    pass
                
                # Properly check if 2FA is enabled - default to False
                result['has_2fa'] = False
                
                # Try to detect 2FA status more accurately
                try:
                    # Try to get full user info that might have 2FA status
                    if hasattr(full_user, 'full_user') and hasattr(full_user.full_user, 'has_password'):
                        result['has_2fa'] = full_user.full_user.has_password
                except:
                    pass
                
                # If we still don't know, try with password hint API
                if not result.get('has_2fa'):
                    try:
                        # This might trigger a password request if 2FA is enabled
                        await client.get_password_hint()
                    except SessionPasswordNeededError:
                        result['has_2fa'] = True
                    except:
                        # Another error occurred, unsure about 2FA - will try other methods
                        pass
                
                # Try to get creation date (estimation based on user ID)
                try:
                    # This is a rough estimation, not 100% accurate
                    timestamp = ((me.id >> 32) - 1420070400)
                    if timestamp > 0:
                        result['creation_date'] = datetime.fromtimestamp(timestamp)
                except Exception as e:
                    print(f"Error getting creation date: {e}")
                    result['creation_date'] = None
            except Exception as e:
                print(f"Error getting user info: {e}")
                # Session is still valid but we couldn't get user info
                result['error_details'] = str(e)
        else:
            result['error'] = "Session gak valid"
    except SessionPasswordNeededError:
        # This is actually a valid session, but with 2FA enabled
        result['valid'] = True
        result['has_2fa'] = True
        
        # Try to get password hint
        try:
            hint = await client.get_password_hint()
            result['password_hint'] = hint if hint else "Tidak ada"
        except:
            result['password_hint'] = "Tidak ada"
            
        # Get other basic info from database (might be limited)
        try:
            me = await client.get_me(input_peer=True)
            if hasattr(me, 'user_id'):
                result['user_id'] = me.user_id
        except:
            pass
    except PhoneNumberInvalidError:
        result['error'] = "Nomor telepon dalam session gak valid"
    except PhoneNumberBannedError:
        result['error'] = "Nomor telepon dalam session udah dibanned"
    except AuthKeyError:
        result['error'] = "Session key gak valid"
    except FloodWaitError as e:
        result['error'] = f"Rate limited, tunggu {e.seconds} detik"
    except Exception as e:
        print(f"Error in check_session_file: {e}")
        traceback.print_exc()
        result['error'] = str(e)
    finally:
        # Disconnect client
        if client:
            try:
                await client.disconnect()
            except:
                pass
            
            # Add a small delay before cleanup
            await asyncio.sleep(0.5)
    
    return result

async def shutdown(signal, loop):
    """Clean shutdown of the bot."""
    print(f"Received exit signal {signal.name}...")
    
    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    if tasks:
        print(f"Cancelling {len(tasks)} tasks...")
        for task in tasks:
            task.cancel()
        
        # Wait for tasks to finish with timeout
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Clean up temporary files
    cleanup_temp_files()
    
    # Stop the bot
    if bot:
        await bot.disconnect()
    
    loop.stop()

async def main():
    # Initialize bot
    if not await init_bot():
        print("Failed to initialize bot. Exiting.")
        return
    
    # Ensure directories exist
    ensure_temp_dirs()
    
    # Load saved sessions
    load_sessions()
    
    # Register event handlers
    bot.add_event_handler(start)
    bot.add_event_handler(kelola)
    bot.add_event_handler(handle_message)
    bot.add_event_handler(handle_page_callback)
    bot.add_event_handler(handle_session_callback)
    bot.add_event_handler(refresh_session_info)
    bot.add_event_handler(back_to_list)
    bot.add_event_handler(get_otp)
    bot.add_event_handler(clear_chat_history)
    bot.add_event_handler(clear_otp_chat_history)
    bot.add_event_handler(confirm_delete_session)
    bot.add_event_handler(delete_session)
    
    # Register new invite handlers
    bot.add_event_handler(invite_contacts_setup)
    bot.add_event_handler(handle_invite_setup_messages)
    bot.add_event_handler(start_invite_process)
    
    print("Bot telah dijalankan...")
    
    # Keep the bot running
    await bot.run_until_disconnected()

if __name__ == "__main__":
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for s in signals:
        try:
            loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(shutdown(s, loop))
            )
        except NotImplementedError:
            # Windows doesn't support adding signal handlers to the event loop
            pass
    
    # Run the bot
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
    finally:
        # Clean up and close the loop
        cleanup_temp_files()
        loop.close()
