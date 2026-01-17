import paho.mqtt.client as mqtt
import time
import threading
import tkinter as tk
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import datetime
import os
import re

# MQTT Configuration
MQTT_BROKER = "192.168.15.101"  # MQTT broker address
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/adc"  # Topic to receive ADC data
directory = "./logs"  # Path where files will be saved

class RealTimePlot:
    def __init__(self, root):
        self.root = root
        self.root.title("Datalogger ESP32C3 ADC via MQTT")

        self.directory = directory  # Define directory in instance
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)  # Create directory if it doesn't exist

        # Create two subplots for two channels
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))

        # Configure line for each ADC
        self.line1, = self.ax1.plot([], [], label='Channel 1')
        self.line2, = self.ax2.plot([], [], label='Channel 2')

        # Configure plot axes
        self.ax1.set_ylim(-100, 4200)
        self.ax1.set_xlabel('Time (ms)')
        self.ax1.set_ylabel('ADC Value')
        self.ax1.set_title('ADC Data - Channel 1')
        self.ax1.grid(True)
        self.ax1.legend(loc='upper right')

        self.ax2.set_ylim(-100, 4200)
        self.ax2.set_xlabel('Time (ms)')
        self.ax2.set_ylabel('ADC Value')
        self.ax2.set_title('ADC Data - Channel 2')
        self.ax2.grid(True)
        self.ax2.legend(loc='upper right')

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack()
        self.fig.subplots_adjust(bottom=0.2, hspace=0.8)

        # MQTT Configuration
        self.mqtt_frame = tk.Frame(root)
        self.mqtt_frame.pack()

        self.broker_label = tk.Label(self.mqtt_frame, text="MQTT Broker:")
        self.broker_label.pack(side=tk.LEFT)
        self.broker_entry = tk.Entry(self.mqtt_frame)
        self.broker_entry.insert(0, MQTT_BROKER)
        self.broker_entry.pack(side=tk.LEFT)

        self.port_label = tk.Label(self.mqtt_frame, text="Port:")
        self.port_label.pack(side=tk.LEFT)
        self.port_entry = tk.Entry(self.mqtt_frame, width=6)
        self.port_entry.insert(0, str(MQTT_PORT))
        self.port_entry.pack(side=tk.LEFT)

        self.topic_label = tk.Label(self.mqtt_frame, text="Topic:")
        self.topic_label.pack(side=tk.LEFT)
        self.topic_entry = tk.Entry(self.mqtt_frame)
        self.topic_entry.insert(0, MQTT_TOPIC)
        self.topic_entry.pack(side=tk.LEFT)

        # First row: ADC Configuration
        self.adc_frame = tk.Frame(root)
        self.adc_frame.pack()

        self.freq_label = tk.Label(self.adc_frame, text="Sampling Frequency (Hz):")
        self.freq_label.pack(side=tk.LEFT)
        self.freq_entry = tk.Entry(self.adc_frame)
        self.freq_entry.insert(0, "20000")  
        self.freq_entry.pack(side=tk.LEFT)

        self.duration_label = tk.Label(self.adc_frame, text="Duration (ms):")
        self.duration_label.pack(side=tk.LEFT)
        self.duration_entry = tk.Entry(self.adc_frame)
        self.duration_entry.insert(0, "10000")  
        self.duration_entry.pack(side=tk.LEFT)

        # Second row: Buttons
        self.button_frame = tk.Frame(root)
        self.button_frame.pack()

        self.start_button = tk.Button(self.button_frame, text="Start", command=self.start_plot)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.save_label = tk.Label(self.button_frame, text="Save as:")
        self.save_label.pack(side=tk.LEFT)

        self.save_var = tk.StringVar()
        self.save_var.set("CSV")
        self.save_menu = tk.OptionMenu(self.button_frame, self.save_var, "CSV", "SVG", "PNG")
        self.save_menu.pack(side=tk.LEFT)

        self.save_button = tk.Button(self.button_frame, text="Save", command=self.save_data)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.mqtt_client = None
        self.collecting_data = False
        self.data_thread = None
        self.frequency = 20000  
        self.duration = 10000
        self.data_buffer = bytearray()  

        # Initialize x and y vectors for both channels
        self.time_stamps = np.round(np.linspace(0, self.duration, num=int(self.duration * self.frequency / 1000) + 1), 6)
        self.data1 = np.zeros_like(self.time_stamps)
        self.data2 = np.zeros_like(self.time_stamps)

        self.ani = animation.FuncAnimation(
            self.fig,
            self.update_plot,
            init_func=self.init_plot,
            interval=100,
            blit=True,
            cache_frame_data=False
        )

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"Successfully connected to MQTT broker")
            topic = self.topic_entry.get()
            client.subscribe(topic)
            print(f"Subscribed to topic: {topic}")
        else:
            print(f"MQTT connection failed. Return code: {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        if self.collecting_data:
            # Add received data to buffer
            self.data_buffer.extend(msg.payload)

    def start_plot(self):
        # Restart data collection and variables
        self.collecting_data = False
        if self.data_thread is not None and self.data_thread.is_alive():
            self.data_thread.join()

        self.frequency = int(self.freq_entry.get())
        self.duration = int(self.duration_entry.get())

        # Update x and y vectors
        self.time_stamps = np.round(np.linspace(0, self.duration, num=int(self.duration * self.frequency / 1000) + 1), 6)
        self.data1 = np.zeros_like(self.time_stamps)
        self.data2 = np.zeros_like(self.time_stamps)

        # Update line data
        self.line1.set_data(self.time_stamps, self.data1)
        self.line2.set_data(self.time_stamps, self.data2)

        # Update plot labels
        self.ax1.set_xlim(0, self.time_stamps[-1])
        self.ax1.set_title(f'ADC Data - Channel 1 (Freq: {self.frequency} Hz, Dur: {self.duration} ms)')
        self.ax2.set_title(f'ADC Data - Channel 2 (Freq: {self.frequency} Hz, Dur: {self.duration} ms)')
        self.ax1.legend(loc='upper right')
        self.ax2.legend(loc='upper right')
        self.canvas.draw()

        # Connect to MQTT broker
        broker = self.broker_entry.get()
        port = int(self.port_entry.get())
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        
        try:
            self.mqtt_client.connect(broker, port, 60)
            self.mqtt_client.loop_start()
            print(f"Connecting to MQTT broker at {broker}:{port}")
            self.start_time = time.time()
            
            # Clear data buffer
            self.data_buffer = bytearray()
            
            # Start data collection
            self.collecting_data = True
            self.data_thread = threading.Thread(target=self.collect_data)
            self.data_thread.start()
        except Exception as e:
            print(f"Error connecting to MQTT broker: {e}")

    def collect_data(self):
        index1 = 0  # Index for channel 1 (ESP32 channel 2)
        index2 = 0  # Index for channel 2 (ESP32 channel 3)
        first_data_received = False
        
        while self.collecting_data and (index1 < len(self.data1) or index2 < len(self.data2)):
            # Check if there is enough data in buffer (4 bytes = 1 sample)
            if len(self.data_buffer) >= 4:
                # Extract 4 bytes from buffer
                new_data = bytes(self.data_buffer[:4])
                self.data_buffer = self.data_buffer[4:]
                
                # Parse 32-bit struct
                sample_uint32 = int.from_bytes(new_data, byteorder='little')
                
                # Extract bit fields
                adc_data = sample_uint32 & 0xFFF  # bits 0-11 (12 bits)
                channel = (sample_uint32 >> 13) & 0x7  # bits 13-15 (3 bits)
                
                if not first_data_received:
                    self.first_data_time = time.time()
                    elapsed_time = self.first_data_time - self.start_time
                    print(f"Time elapsed until first data: {elapsed_time:.6f} seconds")
                    first_data_received = True
                
                # Map ESP32 channels to our channels
                # ESP32 channel 2 -> our channel 1
                # ESP32 channel 3 -> our channel 2
                if channel == 2 and index1 < len(self.data1):
                    self.data1[index1] = adc_data
                    index1 += 1
                elif channel == 3 and index2 < len(self.data2):
                    self.data2[index2] = adc_data
                    index2 += 1
            else:
                # Wait for more data
                time.sleep(0.001)
        
        self.collecting_data = False

    def get_sampling_info(self):
        return f"Frequency: {self.frequency} Hz, Duration: {self.duration} ms"

    def init_plot(self):
        self.line1.set_data(self.time_stamps, self.data1)
        self.line2.set_data(self.time_stamps, self.data2)
        return self.line1, self.line2

    def update_plot(self, frame):
        # Update line data
        self.line1.set_data(self.time_stamps, self.data1)
        self.line2.set_data(self.time_stamps, self.data2)

        # Update legends
        self.ax1.legend(loc='upper right')
        self.ax2.legend(loc='upper right')

        # Update axis limits
        self.ax1.set_xlim(0, self.time_stamps[-1])
        self.ax2.set_xlim(0, self.time_stamps[-1])

        self.canvas.draw()
        return self.line1, self.line2

    def save_data(self):
        save_format = self.save_var.get()
        if save_format == "CSV":
            self.save_csv()
        elif save_format == "SVG":
            self.save_vector()
        elif save_format == "PNG":
            self.save_png()

    def get_base_filename(self):
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
        return f"log_{timestamp}"

    def save_csv(self):
        base_name = self.get_base_filename()
        file_name = f"{base_name}.csv"
        file_path = os.path.join(self.directory, file_name)

        df = pd.DataFrame({
            'time': self.time_stamps,
            'ch1': self.data1,
            'ch2': self.data2
        })
        df.to_csv(file_path, index=False)
        print(f"Data saved to {file_path}")

    def save_vector(self):
        base_name = self.get_base_filename()
        file_name = f"{base_name}.svg"
        file_path = os.path.join(self.directory, file_name)

        self.ax1.set_title(f'ADC Data - Channel 1\nSampling: {self.get_sampling_info()}')
        self.ax2.set_title(f'ADC Data - Channel 2\nSampling: {self.get_sampling_info()}')
        self.fig.savefig(file_path, format='svg')
        print(f"Data saved to {file_path}")

    def save_png(self):
        base_name = self.get_base_filename()
        file_name = f"{base_name}.png"
        file_path = os.path.join(self.directory, file_name)

        self.ax1.set_title(f'ADC Data - Channel 1\nSampling: {self.get_sampling_info()}')
        self.ax2.set_title(f'ADC Data - Channel 2\nSampling: {self.get_sampling_info()}')
        self.fig.savefig(file_path, format='png')
        print(f"Data saved to {file_path}")

if __name__ == "__main__":
    root = tk.Tk()
    plotter = RealTimePlot(root)
    root.mainloop()
