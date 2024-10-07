import os
import time
import socket
import threading
import pygame
import pyaudio
import cv2
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
                    current_time = datetime.now()
                    text_gaze_times.append(current_time)
                    
                    
# Gaze Monitoring
                    
                    
                    
# Audio playback
def play_audio_file(window, file_path):
    global audio_playing, audio_start_time, first_mic_activity_after_audio_detected, audio_playing_time
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
    audio_playing_time = 0  # Reset the counter for every playback

    # Start a separate thread to log audio events every second
    threading.Thread(target=log_audio_events, daemon=True).start()

def log_audio_events():
    global audio_playing, audio_playing_time
    while audio_playing:
        time.sleep(1)
        audio_playing_time += 1
        current_time = datetime.now()
        # event_message = f'[Audio Playing at {audio_playing_time} sec]'
        audio_playback_times.append(current_time)
       # print(event_message)  # Potentially having event timeline outputted as a json aswell?
        
def stop_audio():
    global audio_playing
    if audio_playing:
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        audio_playing = False
        print("Audio stopped.")

# Mic monitoring
def monitor_mic(window, threshold=300):
    global first_mic_activity_after_audio_detected
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
    last_update_time = datetime.now()

    while True:
        data = np.frombuffer(stream.read(1024, exception_on_overflow=False), dtype=np.int16)
        if (volume_level := np.abs(data).mean()) > threshold:
            current_time = datetime.now()
            if (current_time - last_update_time).total_seconds() >= 0.1:
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

# Webcam feed capturing function
def update_webcam(window):
    cap = cv2.VideoCapture(0)  # Use the default camera
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.resize(frame, (320, 240))  # Resize for better display
        imgbytes = cv2.imencode('.png', frame)[1].tobytes()  # Convert the frame to PNG bytes
        window.write_event_value('-WEBCAM-FRAME-', imgbytes)

    cap.release()


def update_graph(ax, x_min=None, x_max=None):
    ax.clear()  
    ax.set_title('Event Timeline', fontsize=14, fontweight='bold')
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Events', fontsize=12)
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))

    # Set grid
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='gray')

    # Set colors for markers
    colors = {'Text Gaze': 'blue', 'Mic Activity': 'red', 'Audio': 'green'}
    events = {
        'Text Gaze': text_gaze_times,
        'Mic Activity': mic_activity_times,
        'Audio': audio_playback_times
    }

    # Plot the events
    for i, (event_label, event_times) in enumerate(events.items()):
        if not event_times:
            continue

        # Plot the events
        ax.plot(event_times, [i] * len(event_times), 'o', label=event_label, color=colors[event_label], markersize=6)

        # Shade clusters within 3 seconds
        for j in range(1, len(event_times)):
            if (event_times[j] - event_times[j - 1]).total_seconds() <= 1.5:
                ax.fill_betweenx([i - 0.3, i + 0.3], event_times[j - 1], event_times[j], color=colors[event_label], alpha=0.2)

    if any(events.values()):
        ax.legend(frameon=False, fontsize=10)
    
    # Set y-ticks to avoid clutter
    ax.set_yticks(list(range(len(events))))
    ax.set_yticklabels(list(events.keys()), fontsize=10)

    # Set x-limits if provided, else use all event times
    if x_min is not None and x_max is not None:
        ax.set_xlim(x_min, x_max)
    else:
        # Set limits to encompass all events if no specific limits are provided
        all_event_times = text_gaze_times + mic_activity_times + audio_playback_times
        if all_event_times:
            ax.set_xlim(min(all_event_times), max(all_event_times))



def draw_figure(canvas_elem):
    fig, ax = plt.subplots(figsize=(15, 7.5))  
    fig.patch.set_facecolor('white')
    canvas = FigureCanvasTkAgg(fig, canvas_elem.TKCanvas)
    canvas.draw()
    canvas.get_tk_widget().pack(side='top')
    return fig, ax, canvas

# GUI Setup

def create_gui():
    layout = [
        [sg.Canvas(key='-CANVAS-', size=(1000, 750), pad=(0, 0))],
        [sg.Slider(range=(0, 100), orientation='h', size=(40, 15), key='-SCROLL-', enable_events=True)],  # Add a slider for scrolling
        [
            sg.Column(
                [
                    [
                        sg.Text('Enter Text to be Displayed:', size=(30, 1)),  
                        sg.InputText(size=(50, 1), key='-INPUT-'), 
                        sg.Button('Send to Unity', size=(20, 1))
                    ],
                    [
                        sg.Text('Audio File:', size=(30, 1)),  
                        sg.InputText(size=(50, 1), key='-AUDIO-FILE-'), 
                        sg.FileBrowse(file_types=(("MP3 Files", "*.mp3"),), size=(20, 1)), 
                    ],
                    [
                        sg.Button('Play Audio', size=(20, 1)), 
                        sg.Button('Stop Audio', size=(20, 1)),
                        sg.Button('Exit', size=(20, 1))  
                    ]
                ],
                vertical_alignment='top',
                size=(800, 850),
                element_justification='left'
            ),
            sg.Column(
                [
                    [sg.Text('Live Mouth Feed', font=('Helvetica', 16, 'bold'), pad=(10, 10))],
                    [sg.Image(key='-WEBCAM-', size=(640, 480))]  # Webcam feed column
                ],
                vertical_alignment='top',
                size=(640, 540)  # Fixed width for the webcam feed
            )
        ],
    ]

    return sg.Window('Session Mode - Speech Pathology XR', layout, finalize=True, resizable=True, size=(1920, 1080), location=(0, 0))





# Session Mode
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
    threading.Thread(target=update_webcam, args=(window,), daemon=True).start()

    # Set initial time range
    time_range = 1  # Viewable range in minutes
    x_min = datetime.now()
    x_max = x_min + np.timedelta64(time_range, 'm')
    
    while True:
        event, values = window.read(timeout=100)
        if event in (sg.WIN_CLOSED, 'Exit'):
            # Save data to JSON before closing
            save_data_to_json()
            break
        elif event == 'Send to Unity':
            message = values['-INPUT-']
            send_to_unity(message)
        elif event == 'Play Audio':
            play_audio_file(window, values['-AUDIO-FILE-'])
        elif event == 'Stop Audio':
            stop_audio()   
        elif event == '-WEBCAM-FRAME-':
            window['-WEBCAM-'].update(data=values['-WEBCAM-FRAME-'])
        elif event == '-SCROLL-':
            scroll_value = values['-SCROLL-'] / 100  # Normalize to range 0-1
            all_times = text_gaze_times + mic_activity_times + audio_playback_times
            if all_times:
                overall_min = min(all_times)
                overall_max = max(all_times)
                total_range = (overall_max - overall_min).total_seconds()
                
                # Calculate offset based on scroll value
                scroll_value = values['-SCROLL-'] / 100  # Normalize to range 0-1
                offset = total_range * scroll_value
                
                new_x_min = overall_min + np.timedelta64(int(-offset), 's')
                new_x_max = overall_max + np.timedelta64(int(-offset), 's')

                  # Ensure new_x_min is less than new_x_max
                if new_x_min >= new_x_max:
                    new_x_min = overall_min
                    new_x_max = overall_max
                    
                update_graph(ax, new_x_min, new_x_max)
                canvas.draw()

        update_graph(ax, x_min, x_max)  # Refresh graph based on latest min and max
        canvas.draw()

    window.close()

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
        [sg.Slider(range=(0, 100), orientation='h', size=(40, 15), key='-REVIEW-SCROLL-', enable_events=True)],
        [sg.Button('Back')]
    ]
    review_window = sg.Window('Review Mode', layout, finalize=True, resizable=True, size=(1920, 1080), location=(0, 0))
    fig, ax, canvas = draw_figure(review_window['-REVIEW-CANVAS-'])

    # Determine the time range based on available event times
    all_times = text_gaze_times + mic_activity_times + audio_playback_times
    x_min = min(all_times) if all_times else datetime.now()
    x_max = max(all_times) if all_times else x_min + np.timedelta64(1, 'm')  # Default to 1 minute if no events

    update_graph(ax, x_min, x_max)
    canvas.draw()

    while True:
        event, values = review_window.read()
        if event in (sg.WIN_CLOSED, 'Back'):
            break
        elif event == '-REVIEW-SCROLL-':
            # Adjust x-axis limits based on slider value
            scroll_value = values['-REVIEW-SCROLL-'] / 100  # Normalize to range 0-1
            if text_gaze_times or mic_activity_times or audio_playback_times:
                min_time = min(all_times)
                max_time = max(all_times)
                offset = (max_time - min_time) * scroll_value
                new_x_min = min_time - offset
                new_x_max = max_time - offset
                update_graph(ax, new_x_min, new_x_max)
                canvas.draw()

    review_window.close()

# Main program execution
def main():
    layout = [
        [sg.Text('Welcome to the Speech Pathology Program', font=('Helvetica', 24), pad=(10, 20))],
        [sg.Column([[sg.Button('Session Mode'), sg.Button('Review Mode')]], justification='center', element_justification='center', expand_x=True)],
        [sg.Column([[sg.Button('Exit', size=(10, 1))]], justification='center', element_justification='center', expand_x=True)]  # Centering the Exit button
]

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
