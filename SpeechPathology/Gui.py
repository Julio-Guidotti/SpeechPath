import os
import socket
import threading
import pygame
import pyaudio
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import PySimpleGUI as sg
from matplotlib.dates import DateFormatter
import json

# Global Variables
pathToFile = None
text_gaze_times, mic_activity_times, audio_playback_times = [], [], []
time_differences_audio_mic, time_differences_text_gaze = [], []
audio_playing, first_mic_activity_after_audio_detected = False, False
audio_start_time = None

# Socket communication with Unity
def send_to_unity(message, host='127.0.0.1', port=5001):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(message.encode('utf-8'))
    except ConnectionRefusedError:
        print("Unity server connection failed.")

def start_server(window, host='127.0.0.1', port=5000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen(1)
        print(f"Listening on {host}:{port}")
        while True:
            client_socket, addr = s.accept()
            print(f"Connection from {addr}")
            with client_socket:
                while data := client_socket.recv(1024):
                    message = data.decode('utf-8')
                    window.write_event_value('NewMessage', f'{message}\n')

# Audio playback
def play_audio_file(window, file_path):
    global audio_playing, audio_start_time, first_mic_activity_after_audio_detected
    if audio_playing:
        print("Audio already playing.")
        return

    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

    audio_start_time = datetime.now()
    event_message = f'[Audio Playback] {audio_start_time.strftime("%Y-%m-%d %H:%M:%S")}'
    audio_playback_times.append(audio_start_time)
    audio_playing = True
    first_mic_activity_after_audio_detected = False

def stop_audio():
    global audio_playing
    if audio_playing:
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        audio_playing = False
        print("Audio stopped.")

# Mic monitoring
def monitor_mic(window, threshold=500):
    global first_mic_activity_after_audio_detected
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
    last_update_time = datetime.now()

    while True:
        data = np.frombuffer(stream.read(1024, exception_on_overflow=False), dtype=np.int16)
        if (volume_level := np.abs(data).mean()) > threshold:
            current_time = datetime.now()
            if (current_time - last_update_time).total_seconds() >= 1:
                log_mic_activity(window, current_time)
                last_update_time = current_time

    stream.stop_stream()
    stream.close()
    p.terminate()

def log_mic_activity(window, current_time):
    global first_mic_activity_after_audio_detected
    event_message = f'[Mic Activity] {current_time.strftime("%Y-%m-%d %H:%M:%S")}'
    
    if audio_start_time and not first_mic_activity_after_audio_detected:
        time_diff = (current_time - audio_start_time).total_seconds()
        time_differences_audio_mic.append(time_diff)
        first_mic_activity_after_audio_detected = True
    
    window.write_event_value('MicActivity', event_message)
    mic_activity_times.append(current_time)

# Graph functions for medical-style graphs
def update_graph(ax):
    ax.clear()
    ax.set_title('Event Timeline', fontsize=14, fontweight='bold')
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Events', fontsize=12)
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))

    # Set grid
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='gray')

    # Set colors for markers
    colors = {'Text Gaze': 'blue', 'Mic Activity': 'red', 'Audio Playback': 'green'}
    events = {
        'Text Gaze': text_gaze_times,
        'Mic Activity': mic_activity_times,
        'Audio Playback': audio_playback_times
    }

    for i, (event_label, event_times) in enumerate(events.items()):
        if not event_times:
            continue

        # Plot the events
        ax.plot(event_times, [i] * len(event_times), 'o', label=event_label, color=colors[event_label], markersize=6)

        # Shade clusters within 3 seconds
        for j in range(1, len(event_times)):
            if (event_times[j] - event_times[j - 1]).total_seconds() <= 3:
                ax.axvspan(event_times[j - 1], event_times[j], color=colors[event_label], alpha=0.2)

    if any(events.values()):
        ax.legend(frameon=False, fontsize=10)

    # Set y-ticks to avoid clutter
    ax.set_yticks(list(range(len(events))))
    ax.set_yticklabels(list(events.keys()), fontsize=10)



def draw_figure(canvas_elem):
    fig, ax = plt.subplots(figsize=(8, 4))  # Wider figure for a better layout
    fig.patch.set_facecolor('white')  # White background
    canvas = FigureCanvasTkAgg(fig, canvas_elem.TKCanvas)
    canvas.draw()
    canvas.get_tk_widget().pack(side='top', fill='both', expand=1)
    return fig, ax, canvas

# Average time display
def display_average_time(window, time_diffs, label):
    if time_diffs:
        avg_time = sum(time_diffs) / len(time_diffs)
        message = f'Average time between {label}: {avg_time:.2f} seconds\n'
    else:
        message = f'No activity detected after {label}.\n'
    

# GUI setup
def create_gui():
    layout = [
            [sg.Canvas(key='-CANVAS-', size=(600, 400), expand_x=True, expand_y=True)],
            [sg.Text('Enter Text to be Displayed:'), sg.InputText(size=(75, 1), key='-INPUT-'), sg.Button('Send to Unity')],
            [sg.Text('Audio File:'), sg.InputText(key='-AUDIO-FILE-'), sg.FileBrowse(file_types=(("MP3 Files", "*.mp3"),)),sg.Button('Play Audio'), sg.Button('Stop Audio')],
            [sg.Button('Exit')]
    ]
    return sg.Window('Session Mode - Speech Pathology XR', layout, finalize=True, resizable=True, size=(1920, 1080), location=(0, 0))

# Session Mode workflow
def session_mode():
    global pathToFile
    pathToFile = sg.popup_get_folder('Select or create a folder for this session')
    
    if not pathToFile:
        sg.popup('No folder selected. Exiting session mode.')
        return
    
    window = create_gui()
    fig, ax, canvas = draw_figure(window['-CANVAS-'])

    threading.Thread(target=start_server, args=(window,), daemon=True).start()
    threading.Thread(target=monitor_mic, args=(window,), daemon=True).start()

    while True:
        event, values = window.read(timeout=100)
        if event in (sg.WIN_CLOSED, 'Exit'):
            # Save data to JSON before closing
            save_data_to_json()
            break
        elif event == 'Send to Unity':
            message = values['-INPUT-']
            send_to_unity(message)
            log_text_gaze(window)
        elif event == 'Play Audio':
            play_audio_file(window, values['-AUDIO-FILE-'])
        elif event == 'Stop Audio':
            stop_audio()
        elif event == 'Display Avg Time (Audio-Mic)':
            display_average_time(window, time_differences_audio_mic, "audio playback and mic activity")
        elif event == 'Display Avg Time (Text Gaze-Mic)':
            display_average_time(window, time_differences_text_gaze, "text gaze and mic activity")

        update_graph(ax)
        canvas.draw()

    window.close()

def log_text_gaze(window):
    current_time = datetime.now()
    text_gaze_times.append(current_time)

def save_data_to_json():
    global pathToFile
    data = {
        'text_gaze_times': [time.isoformat() for time in text_gaze_times],
        'mic_activity_times': [time.isoformat() for time in mic_activity_times],
        'audio_playback_times': [time.isoformat() for time in audio_playback_times],
        'time_differences_audio_mic': time_differences_audio_mic,
        'time_differences_text_gaze': time_differences_text_gaze
    }
    json_path = os.path.join(pathToFile, 'session_data.json')
    with open(json_path, 'w') as json_file:
        json.dump(data, json_file, indent=4)
    print(f'Data saved to {json_path}')

# Review Mode
def review_mode():
    json_file = sg.popup_get_file('Select JSON file', file_types=(("JSON Files", "*.json"),))
    if not json_file:
        sg.popup('No file selected. Exiting review mode.')
        return
    
    with open(json_file, 'r') as file:
        data = json.load(file)

    global text_gaze_times, mic_activity_times, audio_playback_times, time_differences_audio_mic, time_differences_text_gaze
    text_gaze_times = [datetime.fromisoformat(ts) for ts in data['text_gaze_times']]
    mic_activity_times = [datetime.fromisoformat(ts) for ts in data['mic_activity_times']]
    audio_playback_times = [datetime.fromisoformat(ts) for ts in data['audio_playback_times']]
    time_differences_audio_mic = data['time_differences_audio_mic']
    time_differences_text_gaze = data['time_differences_text_gaze']

    layout = [
        [sg.Text('Review Session Data', font=('Helvetica', 16))],
        [sg.Canvas(key='-REVIEW-CANVAS-', size=(400, 400))],
        [sg.Button('Back')]
    ]
    review_window = sg.Window('Review Mode', layout, finalize=True, resizable=True, size=(1920, 1080), location=(0, 0))

    fig, ax, canvas = draw_figure(review_window['-REVIEW-CANVAS-'])
    update_graph(ax)
    canvas.draw()

    while True:
        event, values = review_window.read()
        if event in (sg.WIN_CLOSED, 'Back'):
            break

    review_window.close()

# Main program execution
def main():
    layout = [[sg.Button('Session Mode'), sg.Button('Review Mode'), sg.Button('Exit')]]
    window = sg.Window('Main Menu', layout, resizable=True)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Exit':
            break
        elif event == 'Session Mode':
            session_mode()
        elif event == 'Review Mode':
            review_mode()

    window.close()

if __name__ == "__main__":
    main()
