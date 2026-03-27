import tkinter as tk
from tkinter import ttk, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import threading
import time
import json
import os
from PIL import Image, ImageTk
import pyvirtualcam
import numpy as np

from ArtisanConn import ArtisanConn

class ApplicationError(Exception):
    """Base exception for this app"""
    pass

class Application(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        
        # Configuration
        self.config_file = "config.json"
        self.is_connected = False
        self.loading_status = False
        self.thickness = 0
        self.cam_width = 1024
        self.cam_height = 1280

        # Initialize new config parameters with defaults
        self.debug = False
        self.camera_device = 'Unity Video Capture'
        self.toolhead_id = 14
        self.toolhead_focal = True
        self.photo_coordinates = {'x': 265, 'y': 205, 'z': 330}
        self.photo_speed = 3000
        self.photo_quality = 10
        self.measure_coordinates = {'x': 283, 'y': 203}
        self.measure_speed = 1500
        self.homing_speed = 1500

        # Setup GUI
        self.setup_gui()
        
        # Initialize virtual camera
        self.setup_virtual_cam()
        
        # Load configuration
        self.load_config()

        # Artisan connection
        self.artisan = ArtisanConn(debug=self.debug)
        
        # Auto-connect if enabled
        if self.auto_connect_var.get():
            self.after(100, self.connect)

    def setup_gui(self):
        # Window configuration
        self.title("Snapmaker Artisan Lightburn Assist")
        self.geometry("1040x750")
        self.resizable(False, False)
        
        # Main frame
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel
        left_frame = ttk.Frame(main_frame, width=400)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        left_frame.pack_propagate(False)
        
        # Right panel (camera)
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Connection group
        connection_frame = ttk.LabelFrame(left_frame, text="Connection", padding=10)
        connection_frame.pack(fill=tk.X, pady=(0, 10))
        
        # IP input
        ttk.Label(connection_frame, text="IP Address:").pack(anchor=tk.W)
        self.ip_entry = ttk.Entry(connection_frame)
        self.ip_entry.pack(fill=tk.X, pady=(5, 5))
        
        # Connect button
        self.connect_btn = ttk.Button(connection_frame, text="Connect", command=self.connect)
        self.connect_btn.pack(fill=tk.X)
        
        # Auto-connect checkbox
        self.auto_connect_var = tk.BooleanVar()
        self.auto_connect_cb = ttk.Checkbutton(connection_frame, 
                                             text="Connect automatically",
                                             variable=self.auto_connect_var,
                                             command=self.on_auto_connect_changed)
        self.auto_connect_cb.pack(anchor=tk.W, pady=(10, 0))
        
        # Control buttons group
        control_frame = ttk.LabelFrame(left_frame, text="Controls", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Control buttons
        self.home_btn = ttk.Button(control_frame, text="🏠 Home", 
                                 state=tk.DISABLED, command=self.home)
        self.home_btn.pack(fill=tk.X, pady=(0, 5))
        
        self.update_img_btn = ttk.Button(control_frame, text="📷 Update Image", 
                                       state=tk.DISABLED, command=self.update_image)
        self.update_img_btn.pack(fill=tk.X, pady=(0, 5))
        
        self.thickness_btn = ttk.Button(control_frame, text="📏 Get Thickness", 
                                      state=tk.DISABLED, command=self.get_thickness)
        self.thickness_btn.pack(fill=tk.X, pady=(0, 5))
        
        # New controls: back button, material thickness input, apply button, and set work Z origin
        thickness_frame = ttk.Frame(control_frame)
        thickness_frame.pack(fill=tk.X, pady=(5, 5))
        
        # Back button (narrow)
        self.back_btn = ttk.Button(thickness_frame, text="🔙", width=3,
                                 command=self.reset_thickness_entry)
        self.back_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Material thickness entry
        ttk.Label(thickness_frame, text="Material Thickness:").pack(side=tk.LEFT, padx=(0, 5))
        self.thickness_entry = ttk.Entry(thickness_frame, width=10)
        self.thickness_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.thickness_entry.insert(0, "0")
        
        # Apply button
        self.apply_btn = ttk.Button(thickness_frame, text="✔️ Apply", 
                                  command=self.apply_thickness)
        self.apply_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Set work Z origin button
        self.set_z_origin_btn = ttk.Button(control_frame, text="🎯 Set work Z origin", 
                                         state=tk.DISABLED, command=self.set_work_z_origin)
        self.set_z_origin_btn.pack(fill=tk.X, pady=(5, 0))
        
        # File upload button
        self.upload_btn = ttk.Button(control_frame, text="📤 Upload File", 
                                   state=tk.DISABLED, command=self.upload_file_dialog)
        self.upload_btn.pack(fill=tk.X, pady=(5, 0))

        # Log output group
        log_frame = ttk.LabelFrame(left_frame, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Log text area with scrollbar
        log_scrollbar = ttk.Scrollbar(log_frame)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_frame, height=15, yscrollcommand=log_scrollbar.set)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        log_scrollbar.config(command=self.log_text.yview)
        
        # Camera display
        self.cam_label = ttk.Label(right_frame, background="black")
        self.cam_label.pack(fill=tk.BOTH, expand=True)
        
        # Loading overlay
        self.setup_loading_overlay()

        # Setup drag'n'drop support
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)
        
    def setup_loading_overlay(self):
        self.loading_frame = tk.Frame(self, bg='white', highlightbackground="gray", highlightthickness=2)
        self.loading_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=200, height=100)
        
        loading_label = ttk.Label(self.loading_frame, text="Processing...", font=('Arial', 12))
        loading_label.pack(expand=True, pady=10)
        
        self.progress = ttk.Progressbar(self.loading_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.hide_loading()
        
    def setup_virtual_cam(self):
        """Initialize virtual camera with black image"""
        try:
            # Create black image
            black_image = np.zeros((self.cam_height, self.cam_width, 3), np.uint8)
            
            # Initialize virtual camera
            self.cam = pyvirtualcam.Camera(width=self.cam_width, height=self.cam_height, fps=30, device=self.camera_device)
            self.cam.send(black_image)
            self.cam.sleep_until_next_frame()
            self.cam.send(black_image)
            
            # Update display
            self.update_camera_display(black_image)
            
            self.log(f"Virtual camera '{self.cam.device}' initialized")
        except Exception as e:
            self.log(f"Error initializing virtual camera: {str(e)}")
    
    def update_camera_display(self, image_array):
        """Update the camera display in the GUI"""
        try:
            # Convert numpy array to PIL Image
            image = Image.fromarray(image_array)
            
            # Resize to fit the display while maintaining aspect ratio
            display_width = 600
            display_height = 800
            image.thumbnail((display_width, display_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Update label
            self.cam_label.configure(image=photo)
            self.cam_label.image = photo  # Keep a reference
            
        except Exception as e:
            self.log(f"Error updating camera display: {str(e)}")
    
    def show_loading(self):
        self.loading_frame.lift()
        self.loading_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=200, height=100)
        self.progress.start()
        self.loading_status = True
        
    def hide_loading(self):
        self.loading_frame.place_forget()
        self.progress.stop()
        self.loading_status = False
    
    def log(self, message):
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.update_idletasks()
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.ip_entry.insert(0, config.get('ip_address', ''))
                    self.auto_connect_var.set(config.get('auto_connect', False))
                    
                    # Load new configuration parameters
                    self.debug = config.get('debug', False)
                    self.camera_device = config.get('camera_device', 'Unity Video Capture')
                    self.toolhead_id = config.get('toolhead_id', 14)
                    self.toolhead_focal = config.get('toolhead_id', True)
                    self.photo_coordinates = config.get('photo_coordinates', {'x': 265, 'y': 205, 'z': 330})
                    self.photo_speed = config.get('photo_speed', 3000)
                    self.photo_quality = config.get('photo_quality', 10)
                    self.measure_coordinates = config.get('measure_coordinates', {'x': 283, 'y': 203})
                    self.measure_speed = config.get('measure_speed', 1500)
                    self.homing_speed = config.get('homing_speed', 1500)
                    
        except Exception as e:
            self.log(f"Error loading config: {str(e)}")
            # Set default values if loading fails
            self.debug = False
            self.camera_device = 'Unity Video Capture'
            self.toolhead_id = 14
            self.toolhead_focal = True
            self.photo_coordinates = {'x': 265, 'y': 205, 'z': 330}
            self.photo_speed = 3000
            self.photo_quality = 10
            self.measure_coordinates = {'x': 283, 'y': 203}
            self.measure_speed = 1500
            self.homing_speed = 1500

    def save_config(self):
        try:
            config = {
                'ip_address': self.ip_entry.get(),
                'auto_connect': self.auto_connect_var.get(),
                'debug': self.debug,
                'camera_device': self.camera_device,
                'toolhead_id': self.toolhead_id,
                'toolhead_focal': self.toolhead_focal,
                'photo_coordinates': self.photo_coordinates,
                'photo_speed': self.photo_speed,
                'photo_quality': self.photo_quality,
                'measure_coordinates': self.measure_coordinates,
                'measure_speed': self.measure_speed,
                'homing_speed': self.homing_speed
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            self.log(f"Error saving config: {str(e)}")
    
    def connect(self):
        def connect_thread():
            self.show_loading()
            try:
                self.log("Connecting to device...")
                self.artisan.connect(self.ip_entry.get())
                self.after(0, self.on_connect_success)
                
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self.on_connect_error(error_msg))
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def on_connect_success(self):
        self.is_connected = True
        self.ip_entry.config(state=tk.DISABLED)
        self.connect_btn.config(text="Disconnect", command=self.disconnect)
        self.auto_connect_cb.config(state=tk.NORMAL)
        self.home_btn.config(state=tk.NORMAL)
        self.update_img_btn.config(state=tk.NORMAL)
        self.thickness_btn.config(state=tk.NORMAL)
        self.set_z_origin_btn.config(state=tk.NORMAL)
        self.upload_btn.config(state=tk.NORMAL)
        
        self.save_config()
        self.hide_loading()
        self.log("Connected successfully")
    
    def on_connect_error(self, error_msg):
        self.hide_loading()
        messagebox.showerror("Connection Error", f"Failed to connect: {error_msg}")
        self.log(f"Connection failed: {error_msg}")
    
    def on_auto_connect_changed(self):
        if self.is_connected:
            self.save_config()

    def disconnect(self):
        self.artisan.disconnect()

        self.is_connected = False
        self.ip_entry.config(state=tk.NORMAL)
        self.connect_btn.config(text="Connect", command=self.connect)
        self.home_btn.config(state=tk.DISABLED)
        self.update_img_btn.config(state=tk.DISABLED)
        self.thickness_btn.config(state=tk.DISABLED)
        self.set_z_origin_btn.config(state=tk.DISABLED)
        self.upload_btn.config(state=tk.DISABLED)
        
        self.log("Disconnected")
    
    def home(self):
        def home_thread():
            self.show_loading()
            try:
                self.log("Starting homing procedure...")
                self.artisan.home()

                self.after(0, self.on_home_success)
                
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self.on_operation_error("Homing", error_msg))
        
        threading.Thread(target=home_thread, daemon=True).start()
    
    def on_home_success(self):
        self.hide_loading()
        self.log("Check for homing manually")
    
    def update_image(self):
        def update_image_thread():
            self.show_loading()
            try:
                self.log("Checking if homing is done...")
                is_homed = self.artisan.is_homed()
                if not is_homed:
                    raise ApplicationError("Run homing sequence first!")

                self.log("Taking image...")
                self.artisan.execute_gcode('g54')
                self.artisan.take_photo(self.photo_coordinates['x'],
                                        self.photo_coordinates['y'],
                                        self.photo_coordinates['z'] + self.thickness,
                                        self.photo_speed, self.photo_quality)
                
                self.log("Downloading image...")
                image_path = self.artisan.get_photo()
                
                # Load image from file
                image = Image.open(image_path)
                image_array = np.array(image)
                
                # Send to virtual camera
                self.cam.send(image_array)
                self.cam.sleep_until_next_frame()
                self.cam.send(image_array)
                
                # Update display
                self.after(0, lambda: self.on_image_update_success(image_array))
                
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self.on_operation_error("Image Update", error_msg))
        
        threading.Thread(target=update_image_thread, daemon=True).start()
    
    def on_image_update_success(self, image_array):
        self.update_camera_display(image_array)
        self.hide_loading()
        self.log("Image updated successfully")
    
    def get_thickness(self):
        def thickness_thread():
            self.show_loading()
            try:
                self.log("Checking if homing is done...")
                is_homed = self.artisan.is_homed()
                if not is_homed:
                    raise ApplicationError("Run homing sequence first!")

                self.log("Measuring thickness...")
                self.artisan.execute_gcode('g54')
                thickness = self.artisan.get_material_thickness(self.measure_coordinates['x'],
                                                                     self.measure_coordinates['y'],
                                                                     self.measure_speed)
                self.after(0, lambda: self.on_thickness_success(thickness))
                
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self.on_operation_error("Thickness Measurement", error_msg))
        
        threading.Thread(target=thickness_thread, daemon=True).start()
    
    def on_thickness_success(self, thickness):
        self.hide_loading()
        self.thickness_entry.delete(0, tk.END)
        self.thickness_entry.insert(0, f"{thickness:.3f}")
        self.apply_thickness()
    
    def reset_thickness_entry(self):
        """Reset thickness entry to current self.thickness value"""
        self.thickness_entry.delete(0, tk.END)
        self.thickness_entry.insert(0, f"{self.thickness:.3f}")
        self.log("Thickness entry reset to current value")
    
    def apply_thickness(self):
        """Apply the value from thickness entry to self.thickness"""
        try:
            thickness_value = float(self.thickness_entry.get())
            self.thickness = thickness_value
            self.log(f"Thickness set to: {thickness_value:.3f} mm")
            self.log("This thickness will be applied to camera Z pos")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number for thickness")
            self.log("Error: Invalid thickness value entered")
    
    def set_work_z_origin(self):
        """Set work Z origin"""
        def set_z_origin_thread():
            self.show_loading()
            try:
                self.log("Setting work Z origin...")
                self.artisan.set_laser_work_height(target_id=self.toolhead_id,
                                                   material_thickness=self.thickness,
                                                   feed_rate=self.homing_speed,
                                                   use_focal=self.toolhead_focal)
                self.after(0, self.on_set_z_origin_success)
                
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self.on_operation_error("Set Work Z Origin", error_msg))
        
        threading.Thread(target=set_z_origin_thread, daemon=True).start()
    
    def on_set_z_origin_success(self):
        self.hide_loading()
        self.log("Work Z origin set successfully")
    
    def upload_file_dialog(self):
        """Open file dialog and upload selected file"""
        from tkinter import filedialog
        filepath = filedialog.askopenfilename(
            title="Select file to upload",
            filetypes=[("G-code", "*.nc")]
        )
        if filepath:
            self._upload_file(filepath)

    def on_drop(self, event):
            """Handle drag-and-drop file upload (tkinterdnd2)"""
            # event.data may contain curly braces and multiple files separated by space
            data = event.data.strip()
            # Simple handling: support single file (most common use case)
            # Remove surrounding {} if present
            if data.startswith('{') and data.endswith('}'):
                filepath = data[1:-1]
            else:
                filepath = data
            
            if os.path.isfile(filepath):
                self._upload_file(filepath)
            else:
                self.log(f"Invalid drop: {filepath}")

    def _upload_file(self, filepath: str):
        """Internal upload function with loading indicator"""
        def upload_thread():
            self.show_loading()
            try:
                self.log(f"Uploading file: {os.path.basename(filepath)}")
                self.artisan.upload_file(filepath)
                self.after(0, self.on_upload_success)
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda: self.on_operation_error("File Upload", error_msg))
        
        threading.Thread(target=upload_thread, daemon=True).start()

    def on_upload_success(self):
        self.hide_loading()
        self.log("File uploaded successfully")

    def on_operation_error(self, operation, error_msg):
        self.hide_loading()
        messagebox.showerror(f"{operation} Error", f"{operation} failed: {error_msg}")
        self.log(f"{operation} failed: {error_msg}")

if __name__ == "__main__":
    app = Application()
    app.mainloop()

    try:
        app.artisan.disconnect()
    except:
        pass