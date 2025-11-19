import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import json
import requests
import os

# ==========================
#  STYLE
# ==========================
BG = '#1a2026'
BTN_BG = '#2c3742'
BTN_ACCENT = '#3d7bff'
TEXT = '#ffffff'
ENTRY_BG = '#242e38'
ENTRY_FG = '#ffffff'
STATUS_BG = '#212a33'
PROGRESS_GREEN = 'lightgreen' # Color for progress bar
FONT_NORMAL = ('Arial', 13)
FONT_SMALL = ('Arial', 12)
FONT_BTN = ('Arial', 14, 'bold')
FONT_PIXEL_HEIGHT = 17 # Approx px for 13pt font

# Globals for stopping
current_process = None
stop_flag = False

# ==========================
#  HELPER UI FUNCTIONS
# ==========================
def clear_status_label():
    """Clears all status labels"""
    loading_label.config(text='')
    size_label.config(text='')
    speed_label.config(text='')

def reset_ui_state():
    """Clears labels and resets progress bar. Called by Clear and Load."""
    clear_status_label()
    progress.stop()
    progress.config(mode='determinate')
    progress_var.set(0)

def hide_stop_button():
    """Hides the stop button"""
    stop_btn.grid_forget()

def show_stop_button():
    """Shows the stop button"""
    stop_btn.grid(row=0, column=2, sticky='ew')

def on_combo_select(event):
    """Removes the selection highlight from a combobox"""
    event.widget.selection_clear()

def format_bytes(b):
    """Converts bytes to a readable string (KiB, MiB, GiB)"""
    if b is None or b == 'NA': return "N/A"
    try:
        b = float(b)
        if b > 1024*1024*1024:
            return f"{b / (1024*1024*1024):.2f} GiB"
        if b > 1024*1024:
            return f"{b / (1024*1024):.2f} MiB"
        if b > 1024:
            return f"{b / 1024:.2f} KiB"
        return f"{int(b)} B"
    except:
        return str(b) # Return original string if conversion fails

# ==========================
#  CHECK YOUTUBE ACCESS
# ==========================
def check_logic_thread():
    """Runs in thread, updates UI via root.after"""
    try:
        requests.get('https://www.youtube.com', timeout=3)
        root.after(0, lambda: status_label.config(text='YouTube is reachable', fg='lightgreen'))
    except:
        root.after(0, lambda: status_label.config(text='YouTube is NOT reachable', fg='orange'))

def run_check_and_schedule():
    """Called by timer. Sets status, starts thread, schedules next."""
    threading.Thread(target=check_logic_thread, daemon=True).start()
    root.after(5000, run_check_and_schedule) # Reschedule

def run_check_manual(e=None):
    """Called by click. Sets status, starts thread."""
    status_label.config(text='Checking...', fg='orange')
    threading.Thread(target=check_logic_thread, daemon=True).start()

# ==========================
#  CLEAN URL
# ==========================
def clean_url(url):
    """Strips extra parameters from YouTube URLs"""
    cleaned_url = url.split('&')[0] 
    if 'youtu.be/' in cleaned_url:
        cleaned_url = cleaned_url.split('?')[0] 
    return cleaned_url

# ==========================
#  GET AVAILABLE QUALITIES
# ==========================
def get_formats(url):
    try:
        result = subprocess.run(['yt-dlp', '-J', url], capture_output=True, text=True, encoding='utf-8')
        data = json.loads(result.stdout)
        formats = data.get('formats', [])
        
        q_set = {int(f.get('height')) for f in formats if f.get('height')}
        q_sorted = sorted(list(q_set), reverse=True)
        return [str(h) for h in q_sorted]
    
    except Exception as e:
        print(f"DEBUG: get_formats failed: {e}")
        return []

# ==========================
#  LOAD QUALITIES THREAD
# ==========================
def update_qualities_ui(qualities):
    """Updates the combobox and label from the main thread"""
    quality_combo['values'] = qualities
    if qualities:
        count = len(qualities)
        loading_label.config(text=f'{count} qualities found.', fg='lightgreen')
        quality_combo.current(0)
        quality_combo.selection_clear() # Remove highlight
    else:
        loading_label.config(text='No qualities found.', fg='orange')
    
def load_qualities_thread():
    """Runs in background thread"""
    root.after(0, lambda: loading_label.config(text='Loading…', fg='yellow'))
    
    url = clean_url(url_entry.get().strip())
    qualities = get_formats(url) # Blocking call
    
    root.after(0, update_qualities_ui, qualities) 

def load_qualities():
    if not url_entry.get().strip():
        messagebox.showerror('Error', 'Enter YouTube link first.')
        return
    
    reset_ui_state()
    threading.Thread(target=load_qualities_thread, daemon=True).start()

# ==========================
#  STOP DOWNLOAD
# ==========================
def stop_download():
    global stop_flag, current_process
    stop_flag = True
    if current_process:
        try:
            current_process.terminate()
        except:
            pass
            
    loading_label.config(text='Stopped', fg='orange')
    size_label.config(text='')
    speed_label.config(text='')
    
    root.after(0, progress.stop)
    root.after(0, lambda: progress.config(mode='determinate'))
    root.after(0, progress_var.set, 0) # Reset bar
    
    hide_stop_button() 
    
# ==========================
#  DOWNLOAD THREAD
# ==========================
def run_download(url, q, speed):
    global current_process, stop_flag
    stop_flag = False
    
    reset_ui_state()
    root.after(0, lambda: loading_label.config(text='Preparing…', fg='yellow'))

    # Get title
    try:
        info = subprocess.run(['yt-dlp', '--get-title', '--encoding', 'utf-8', url], 
                              capture_output=True, text=True, encoding='utf-8', errors='ignore')
        title = info.stdout.strip()
        print(f"DEBUG: Title stdout: '{info.stdout.strip()}'")
        if not title: 
            print("DEBUG: Title was empty, using 'video'")
            title = 'video'
    except Exception as e:
        print(f"DEBUG: get-title failed: {e}")
        title = 'video' 

    safe_title = ''.join(c for c in title if c not in r'<>:"/\|?*')
    if not safe_title.strip(): 
        safe_title = 'video'
            
    outfile_final = f"{safe_title} ({q} - {speed}x).mp4"
    outfile_temp = f"{safe_title} ({q})_temp.mp4"

    if speed == '1.0':
        outfile_to_use = outfile_final 
    else:
        outfile_to_use = outfile_temp 

    # --- FIX: Removed '--newline' ---
    cmd1 = [
        'yt-dlp',
        '-f', f'(bestvideo[height={q}]+bestaudio)/best[height={q}]', 
        '--merge-output-format', 'mp4',
        '--progress-template', 
        'download-stats:%(progress.downloaded_bytes)s/%(progress.total_bytes)s@%(progress.speed)s#%(progress.percentage)s',
        '-o', outfile_to_use, 
        url
    ]

    current_process = subprocess.Popen(cmd1, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, bufsize=1, encoding='utf-8', errors='ignore')

    output_lines = [] 
    download_started = False
    
    for line in current_process.stdout:
        output_lines.append(line) 
        if stop_flag:
            root.after(0, hide_stop_button) 
            return
        
        if line.startswith('download-stats:'):
            if not download_started:
                root.after(0, lambda: loading_label.config(text='Downloading…', fg='lightgreen'))
                download_started = True

            try:
                stats = line.replace('download-stats:', '').strip()
                parts = stats.split('#')
                size_speed = parts[0].split('@')
                size = size_speed[0].split('/')
                speed_str_bytes = size_speed[1]
                percent_str = parts[1].replace('%', '')

                downloaded_b = size[0]
                total_b = size[1]

                size_text = f"{format_bytes(total_b)} / {format_bytes(downloaded_b)}"
                speed_ui_str = f"{format_bytes(speed_str_bytes)}/s" if speed_str_bytes != 'NA' else "N/A"
                
                # --- FIX: Check for 'NA' in percent string ---
                if percent_str != 'NA':
                    percent_mapped = int(float(percent_str) * 0.8)
                    root.after(0, progress_var.set, percent_mapped)
                
                root.after(0, size_label.config, {'text': size_text})
                root.after(0, speed_label.config, {'text': speed_ui_str})
                root.after(0, loading_label.config, {'text': f'Downloading… ({speed_ui_str})', 'fg': 'lightgreen'})

            except Exception as e:
                print(f"DEBUG: Parsing line failed: {line} -> {e}")
                pass
        # --- End parsing logic ---

    current_process.wait()
    return_code = current_process.returncode 

    if stop_flag:
        root.after(0, hide_stop_button) 
        return
        
    root.after(0, progress_var.set, 80)

    if return_code != 0 or not os.path.exists(outfile_to_use):
        root.after(0, lambda: loading_label.config(text='Download failed (yt-dlp)', fg='red'))
        root.after(0, lambda: size_label.config(text=''))
        root.after(0, lambda: speed_label.config(text=''))
        root.after(0, progress_var.set, 0) # Reset bar on fail
        
        print("\n--- yt-dlp Error Log ---")
        print("".join(output_lines)) 
        print(f"Command: {' '.join(cmd1)}")
        print(f"Return Code: {return_code}")
        print(f"Checked for file: {outfile_to_use} (Exists: {os.path.exists(outfile_to_use)})")
        print("--------------------------\n")

        if os.path.exists(outfile_to_use):
            try:
                os.remove(outfile_to_use)
            except:
                pass 
        root.after(0, hide_stop_button)
        return

    if speed == '1.0':
        root.after(0, progress_var.set, 100) # Finish bar
        root.after(0, lambda: loading_label.config(text='Done', fg='lightgreen'))
        root.after(0, hide_stop_button)
        return 

    root.after(0, lambda: loading_label.config(text='Encoding (ffmpeg)…', fg='yellow'))
    root.after(0, lambda: progress.config(mode='indeterminate'))
    root.after(0, progress.start, 10) # 10ms interval

    cmd2 = [
        'ffmpeg', '-i', outfile_temp, 
        '-filter_complex', f'[0:v]setpts=PTS/{speed}[v];[0:a]atempo={speed}[a]',
        '-map', '[v]', '-map', '[a]',
        '-c:v', 'libx264', '-c:a', 'aac',
        outfile_final 
    ]

    current_process = subprocess.Popen(cmd2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='ignore')
    
    ffmpeg_output, _ = current_process.communicate() 
    return_code_ffmpeg = current_process.returncode
    
    root.after(0, progress.stop)
    root.after(0, lambda: progress.config(mode='determinate'))

    if os.path.exists(outfile_temp):
        try:
            os.remove(outfile_temp)
        except:
            pass 

    if return_code_ffmpeg != 0:
        root.after(0, lambda: loading_label.config(text='Encoding failed (ffmpeg)', fg='red'))
        root.after(0, lambda: size_label.config(text=''))
        root.after(0, lambda: speed_label.config(text=''))
        root.after(0, progress_var.set, 80) # Set bar to 80% on fail
        
        print("\n--- ffmpeg Error Log ---")
        print(ffmpeg_output) 
        print(f"Command: {' '.join(cmd2)}")
        print(f"Return Code: {return_code_ffmpeg}")
        print("--------------------------\n")
        root.after(0, hide_stop_button)
        return

    root.after(0, progress_var.set, 100) # Finish bar
    root.after(0, lambda: loading_label.config(text='Done', fg='lightgreen'))
    root.after(0, hide_stop_button)
    
# ==========================
#  START DOWNLOAD
# ==========================
def start_download():
    url = clean_url(url_entry.get().strip())
    q = quality_var.get()
    speed = speed_var.get()

    if not url or not q:
        messagebox.showerror('Error', 'Please enter URL and select quality first.')
        return
    
    show_stop_button()
    threading.Thread(target=run_download, args=(url, q, speed), daemon=True).start()

# ==========================
#  UI
# ==========================
root = tk.Tk()
root.title('YouTube Downloader')
root.configure(bg=BG)

main_frame = tk.Frame(root, bg=BG)
main_frame.pack(padx=20, pady=20) 

# Paste/Clear shortcuts
def do_paste(e=None):
    try:
        content = root.clipboard_get()
        content = content.strip()
        
        if content.startswith(('http://', 'https://', 'www.youtube.com', 'youtube.com', 'youtu.be')):
            url_entry.delete(0, tk.END) 
            url_entry.insert(0, content) 
        else:
            messagebox.showerror('Invalid Paste', 'The clipboard content does not look like a valid URL.')
            
    except tk.TclError:
        messagebox.showerror('Paste Error', 'Could not read text from clipboard.')
    except Exception as e:
        messagebox.showerror('Error', f'An unexpected error occurred: {e}')

def clear_entry():
    url_entry.delete(0, tk.END)
    reset_ui_state()

root.bind_all('<Control-v>', do_paste)
root.bind_all('<Control-V>', do_paste)

button_height_padding = 6 
entry_inner_height = FONT_PIXEL_HEIGHT + (2 * button_height_padding)

# URL row
url_row = tk.Frame(main_frame, bg=BG)
url_row.pack(pady=(0,5), fill='x') 

url_entry = tk.Entry(url_row, width=45, bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                   relief='flat', font=FONT_NORMAL) 
url_entry.pack(side='left', ipady=button_height_padding, expand=True, fill='x') 

paste_btn = tk.Button(url_row, text='Paste', command=do_paste, bg=BTN_BG, fg=TEXT,
                     bd=0, cursor='hand2', font=FONT_SMALL, padx=12, pady=button_height_padding)
paste_btn.pack(side='left', padx=(8, 0)) 

clear_btn = tk.Button(url_row, text='X', command=clear_entry, bg=BTN_BG, fg=TEXT,
                     bd=0, cursor='hand2', font=FONT_SMALL, padx=8, pady=button_height_padding)
clear_btn.pack(side='left', padx=(4, 0)) 


# Quality + Load + Speed
row = tk.Frame(main_frame, bg=BG)
row.pack(pady=10)

style = ttk.Style()
try:
    style.theme_use('clam')
except tk.TclError:
    style.theme_use('default') 

# Custom style for Combobox
style.configure('TCombobox',
                fieldbackground=ENTRY_BG,
                background=BTN_BG, 
                foreground=ENTRY_FG,
                selectbackground=BTN_ACCENT,
                selectforeground=TEXT,
                arrowcolor=TEXT,
                bordercolor=BG, 
                lightcolor=BG, 
                darkcolor=BG, 
                troughcolor=BTN_BG,
                padding=(5, button_height_padding),
                borderwidth=0,
                relief='flat'
                )
style.map('TCombobox',
          fieldbackground=[('readonly', ENTRY_BG)],
          background=[('readonly', BTN_BG)],
          foreground=[('readonly', ENTRY_FG)]
          )
root.option_add('*TCombobox*Listbox.background', BTN_BG)
root.option_add('*TCombobox*Listbox.foreground', ENTRY_FG)
root.option_add('*TCombobox*Listbox.selectBackground', BTN_ACCENT)
root.option_add('*TCombobox*Listbox.selectForeground', TEXT)
root.option_add('*TCombobox*Listbox.borderwidth', 0) 


# --- FIX: Height doubled from entry height (approx 29*2 = 58 -> 60) ---
style.configure('Horizontal.TProgressbar',
                background=PROGRESS_GREEN,
                troughcolor=ENTRY_BG,
                borderwidth=0,
                bordercolor=BG, 
                relief='flat',
                thickness=60) # Set height to 60px


quality_var = tk.StringVar()
quality_combo = ttk.Combobox(row, textvariable=quality_var, state='readonly', width=10, font=FONT_NORMAL, style='TCombobox')
quality_combo.pack(side='left', padx=5)
quality_combo.configure(justify='center')
quality_combo.bind('<<ComboboxSelected>>', on_combo_select)


load_btn = tk.Button(row, text='Load Qualities', command=load_qualities, bg=BTN_BG, fg=TEXT,
                     bd=0, cursor='hand2', font=FONT_SMALL, padx=12, pady=button_height_padding)
load_btn.pack(side='left', padx=8)

speed_var = tk.StringVar()
speed_combo = ttk.Combobox(row, textvariable=speed_var, state='readonly', width=10, font=FONT_NORMAL, style='TCombobox')
speed_combo['values'] = ['1.0', '1.25', '1.5', '1.75', '2']
speed_combo.current(0)
speed_combo.selection_clear()
speed_combo.bind('<<ComboboxSelected>>', on_combo_select)
speed_combo.pack(side='left', padx=5)
speed_combo.configure(justify='center')

# Stats row
stats_row = tk.Frame(main_frame, bg=BG)
stats_row.pack(pady=(10, 0), fill='x') 

size_label = tk.Label(stats_row, text='', bg=BG, fg=TEXT, font=FONT_SMALL)
size_label.pack(side='left')

speed_label = tk.Label(stats_row, text='', bg=BG, fg=TEXT, font=FONT_SMALL)
speed_label.pack(side='right')

# Progress bar
progress_var = tk.IntVar()
progress = ttk.Progressbar(main_frame, orient='horizontal', mode='determinate', variable=progress_var, style='Horizontal.TProgressbar')
progress.pack(pady=5, fill='x') 

# Buttons
btn_row = tk.Frame(main_frame, bg=BG)
btn_row.pack(pady=10, fill='x')

btn_row.columnconfigure(0, weight=4) 
btn_row.columnconfigure(1, weight=2) 
btn_row.columnconfigure(2, weight=4) 

start_btn = tk.Button(btn_row, text='Download', command=start_download, bg=BTN_ACCENT, fg=TEXT,
                      bd=0, cursor='hand2', font=FONT_BTN, padx=25, pady=10)
start_btn.grid(row=0, column=0, sticky='ew') 

stop_btn = tk.Button(btn_row, text='Stop', command=stop_download, bg='#aa3333', fg=TEXT,
                     bd=0, cursor='hand2', font=FONT_BTN, padx=20, pady=10)


# Status
status_label = tk.Label(main_frame, text='Checking...', bg=BG, fg='orange', font=FONT_SMALL, cursor='hand2')
status_label.pack(side='bottom', fill='x') 
status_label.bind('<Button-1>', run_check_manual)

loading_label = tk.Label(main_frame, text='', bg=BG, fg='yellow', font=FONT_SMALL)
loading_label.pack(side='bottom', fill='x', pady=(0, 2)) 

run_check_and_schedule()
root.mainloop()