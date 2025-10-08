# Snapmaker Artisan LightBurn Toolkit 
 
Tool that allows you to use your Snapmaker Artisan laser in LightBurn. 

# External dependencies
1. https://github.com/schellingb/UnityCapture: virtual DirectShow camera.

To use the Unity Capture virtual camera, follow the [installation instructions](https://github.com/schellingb/UnityCapture#installation) on the project site.

# Python dependencies
1. Pillow
2. pyvirtualcam
3. numpy
4. pyinstaller (for build)

# Usage
1. Download and install Unity Capture virtual camera.
2. Download and run ```dist/main.exe```.
3. Use GUI to connect to your Snapmaker Artisan.
4. In LightBurn settings, verify that ```Default Capture System``` is selected under ```Camera Capture System```.
5. In LightBurn, select ```Unity Video Capture``` as your camera.
6. Enjoy!

# Build
1. Download or pull this repo.
2. Run prepare.bat for install Python dependencies.
3. Run build.bat
