import socket
import PySimpleGUI as sg
import threading
import pygame
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import DateFormatter
import wave
import time

# Arrays for Plotting Data
text_gaze_times = []
mic_activity_times = []
audio_playback_times = []

# Lists to store time differences
time_differences_audio_mic = []
time_differences_text_gaze = []

# Flags
audio_playing = False
audio_start_time = None  # To store the time when audio starts playing
first_mic_activity_after_audio_detected = False

# Send Text to be displayed to Unity
def send_to_unity(message, host='127.0.0.1', port=5001):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unity_socket:
            unity_socket.connect((host, port))
            unity_socket.sendall(message.encode('utf-8'))
    except ConnectionRefusedError:
        print("Could not connect to Unity. Make sure the Unity server is running.")

# Start Server to receive information from Unity
def start_server(window, host='127.0.0.1', port=5000):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(1)

    print(f"Listening on {host}:{port}")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Connection from {addr}")

        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            message = data.decode('utf-8')
            window.write_event_value('NewMessage', message + '\n')

        client_socket.close()

# Function checking Mic Usage
def monitor_mic(window, threshold=500):
    import pyaudio
    global first_mic_activity_after_audio_detected, first_text_gaze_after_mic_detected  # Declare global variables

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, 
                    channels=1, 
                    rate=44100, 
                    input=True, 
                    frames_per_buffer=1024)

    last_update_time = datetime.now()

    while True:
        data = np.frombuffer(stream.read(1024, exception_on_overflow=False), dtype=np.int16)
        volume_level = np.abs(data).mean()

        # Check for activity
        if volume_level > threshold:
            current_time = datetime.now()  # Get the Time
            if (current_time - last_update_time).total_seconds() >= 1:  # Check if 1 second has passed
                current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
                event_message = f'[Mic Activity]   {current_time_str}'

                # Calculate time difference if audio_start_time is set
                if audio_start_time is not None and not first_mic_activity_after_audio_detected:
                    time_diff = (current_time - audio_start_time).total_seconds()
                    time_differences_audio_mic.append(time_diff)
                    diff_message = f'Time since audio started: {time_diff:.2f} seconds'
                    window['-TIMELINE-'].update(diff_message + '\n', append=True)
                    first_mic_activity_after_audio_detected = True

                window.write_event_value('MicActivity', event_message)
                mic_activity_times.append(current_time)
                last_update_time = current_time

    stream.stop_stream()
    stream.close()
    p.terminate()

# Function to play an audio file
def play_audio_file(window, file_path):
    global audio_playing, audio_start_time, first_mic_activity_after_audio_detected
    
    if audio_playing:
        print("Audio is already playing. Stop the current audio before playing a new one.")
        return

    # Initialize pygame mixer
    pygame.mixer.init()

    # Load and play the MP3 file
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

    # Log the time audio playback starts
    audio_start_time = datetime.now()
    start_time_str = audio_start_time.strftime('%Y-%m-%d %H:%M:%S')
    event_message = f'[Audio Playback] {start_time_str}'
    window['-TIMELINE-'].update(event_message + '\n', append=True)
    audio_playback_times.append(audio_start_time)
    
    # Set the flag indicating audio is playing
    audio_playing = True

    # Reset the mic activity flag
    first_mic_activity_after_audio_detected = False

# Function to stop audio playback
def stop_audio():
    global audio_playing
    
    if audio_playing:
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        audio_playing = False
        print("Audio stopped.")

# Function to update the graph with new event times
def update_graph(ax):
    ax.clear()
    ax.set_title('Event Timeline')
    ax.set_xlabel('Time')
    ax.set_ylabel('Events')
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))

    # Plot the events
    if text_gaze_times:
        ax.plot(text_gaze_times, [1] * len(text_gaze_times), 'bo', label='Text Gaze')
    if mic_activity_times:
        ax.plot(mic_activity_times, [1.2] * len(mic_activity_times), 'ro', label='Mic Activity')
    if audio_playback_times:
        ax.plot(audio_playback_times, [1.4] * len(audio_playback_times), 'go', label='Audio Playback')
    if text_gaze_times or mic_activity_times or audio_playback_times: 
        ax.legend()

# Function to create and manage the GUI
def create_gui():
    layout = [
        [
            sg.Column([ 
                [sg.Text('Enter Text to be Displayed:', size=(30, 1), font=("Helvetica", 16))],
                [sg.InputText(size=(75, 1), key='-INPUT-')],
                [sg.Button('Send to Unity')],
                [sg.Text('Timeline:', size=(30, 1), font=("Helvetica", 16))],
                [sg.Multiline(size=(75, 25), key='-TIMELINE-', autoscroll=True, disabled=True)],
                [sg.Text('Audio File:', size=(30, 1), font=("Helvetica", 16))],
                [sg.InputText(key='-AUDIO-FILE-', size=(40, 1)), sg.FileBrowse(file_types=(("MP3 Files", "*.mp3"),))],
                [sg.Button('Play Audio'), sg.Button('Stop Audio')],
                [sg.Button('Display Average Time (Audio-Mic)')],
                [sg.Button('Display Average Time (Text Gaze-Mic)')],
            ]),
            sg.VSeperator(),
            sg.Column([
                [sg.Canvas(key='-CANVAS-', size=(600, 400))]
            ])
        ],
        [sg.Button('Exit')]
    ]

    window = sg.Window('Speech Pathology XR', layout, finalize=True)
    return window

# Function to draw the initial Matplotlib graph
def draw_figure(canvas_elem):
    fig, ax = plt.subplots(figsize=(6, 4))  # Adjust figure size to match Canvas size
    canvas = FigureCanvasTkAgg(fig, canvas_elem.TKCanvas)
    canvas.draw()
    canvas.get_tk_widget().pack(side='top', fill='both', expand=1)
    return fig, ax, canvas

# Function to display the average time between audio playback and mic activity
def display_average_time_audio_mic(window):
    if time_differences_audio_mic:
        average_time = sum(time_differences_audio_mic) / len(time_differences_audio_mic)
        average_message = f'Average time between audio playback and mic activity: {average_time:.2f} seconds'
    else:
        average_message = 'No microphone activity detected after audio playback.'
    
    window['-TIMELINE-'].update(average_message + '\n', append=True)

# Function to display the average time between text gaze and mic activity
def display_average_time_text_gaze_mic(window):
    if time_differences_text_gaze:
        average_time = sum(time_differences_text_gaze) / len(time_differences_text_gaze)
        average_message = f'Average time between text gaze and mic activity: {average_time:.2f} seconds'
    else:
        average_message = 'No microphone activity detected after text gaze.'
    
    window['-TIMELINE-'].update(average_message + '\n', append=True)

# Main function to run the server and GUI
def main():
    global first_text_gaze_after_mic_detected  # Declare global variable

    window = create_gui()

    # Create and display the graph
    fig, ax, canvas = draw_figure(window['-CANVAS-'])

    # Start the server in a separate thread
    server_thread = threading.Thread(target=start_server, args=(window,))
    server_thread.daemon = True
    server_thread.start()

    # Start microphone activity detection in a separate thread
    mic_thread = threading.Thread(target=monitor_mic, args=(window,))
    mic_thread.daemon = True
    mic_thread.start()

    while True:
        event, values = window.read(timeout=100)

        if event in (sg.WIN_CLOSED, 'Exit'):
            break
        elif event == 'Send to Unity':
            message = values['-INPUT-']
            send_to_unity(message)
            current_time = datetime.now()
            current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
            log_message = f'[Text Gaze]      {current_time_str}'
            window['-TIMELINE-'].update(log_message + '\n', append=True)
            text_gaze_times.append(current_time)

            # Calculate the time difference between text gaze and the first mic activity after text gaze
            if mic_activity_times and not first_text_gaze_after_mic_detected:
                last_text_gaze_time = text_gaze_times[-1]
                first_mic_after_text_gaze = None

                for mic_time in mic_activity_times:
                    if mic_time > last_text_gaze_time:
                        first_mic_after_text_gaze = mic_time
                        break

                if first_mic_after_text_gaze:
                    time_diff = (first_mic_after_text_gaze - last_text_gaze_time).total_seconds()
                    time_differences_text_gaze.append(time_diff)
                    diff_message = f'Time between text gaze and first mic activity after: {time_diff:.2f} seconds'
                    window['-TIMELINE-'].update(diff_message + '\n', append=True)
                    first_text_gaze_after_mic_detected = True
                else:
                    diff_message = 'No microphone activity detected after the last text gaze.'
                    window['-TIMELINE-'].update(diff_message + '\n', append=True)

        elif event == 'NewMessage':
            window['-TIMELINE-'].update(values[event], append=True)

        elif event == 'MicActivity':
            window['-TIMELINE-'].update(values[event] + '\n', append=True)

        elif event == 'Play Audio':
            file_path = values['-AUDIO-FILE-']
            if file_path:
                play_audio_file(window, file_path)

        elif event == 'Stop Audio':
            stop_audio()

        elif event == 'Display Average Time (Audio-Mic)':
            display_average_time_audio_mic(window)

        elif event == 'Display Average Time (Text Gaze-Mic)': 
            display_average_time_text_gaze_mic(window)

        update_graph(ax)
        canvas.draw()

    window.close()

if __name__ == "__main__":
    main()