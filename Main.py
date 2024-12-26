import cv2
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np
from urllib.parse import parse_qs, urlparse

def get_camera_info(source_id):
    cap = cv2.VideoCapture(source_id)
    if not cap.isOpened():
        return None
    
    # Get camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Try to get camera name/description
    backend = cap.getBackendName()
    
    # Read one frame to check if camera is working
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        return None
        
    # On Windows, you might get additional camera info
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        cameras = wmi.InstancesOf("Win32_PnPEntity")
        for camera in cameras:
            if "USB" in str(camera.Name) and "Camera" in str(camera.Name):
                return {
                    'id': source_id,
                    'name': camera.Name,
                    'resolution': f"{width}x{height}",
                    'backend': backend
                }
    except:
        pass
    
    # Default camera info if specific name cannot be retrieved
    return {
        'id': source_id,
        'name': f"Camera {source_id}",
        'resolution': f"{width}x{height}",
        'backend': backend
    }

class VideoStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            camera_info = self.server.camera_info
            camera_title = f"{camera_info['name']} ({camera_info['resolution']})"
            
            self.wfile.write(f'''
                <html>
                <head>
                    <title>{camera_title}</title>
                    <style>
                        body {{
                            margin: 0;
                            padding: 0;
                            background: #000;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                            font-family: Arial, sans-serif;
                        }}
                        .container {{
                            position: relative;
                            width: 100%;
                            max-width: 1280px;
                        }}
                        .video-feed {{
                            width: 100%;
                            height: auto;
                            cursor: pointer;
                        }}
                        .fullscreen {{
                            position: fixed;
                            top: 0;
                            left: 0;
                            width: 100%;
                            height: 100%;
                            object-fit: contain;
                            z-index: 9999;
                        }}
                        .controls {{
                            position: fixed;
                            bottom: 20px;
                            left: 50%;
                            transform: translateX(-50%);
                            background: rgba(0, 0, 0, 0.5);
                            padding: 10px 20px;
                            border-radius: 5px;
                            z-index: 10000;
                            transition: opacity 0.3s ease;
                            color: white;
                            text-align: center;
                        }}
                        .controls.hidden {{
                            opacity: 0;
                            pointer-events: none;
                        }}
                        .title {{
                            margin-bottom: 10px;
                            font-size: 14px;
                            font-weight: bold;
                        }}
                        button {{
                            background: #fff;
                            border: none;
                            padding: 8px 15px;
                            border-radius: 4px;
                            cursor: pointer;
                            font-size: 14px;
                        }}
                        button:hover {{
                            background: #ddd;
                        }}
                        .controls:hover {{
                            opacity: 1 !important;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <img src="/stream" class="video-feed" id="videoFeed" alt="Video Stream">
                        <div class="controls" id="controls">
                            <div class="title">{camera_title}</div>
                            <button onclick="toggleFullScreen()">Toggle Fullscreen</button>
                        </div>
                    </div>
                    <script>
                        const videoFeed = document.getElementById('videoFeed');
                        const controls = document.getElementById('controls');
                        let controlsTimeout;

                        function toggleFullScreen() {{
                            videoFeed.classList.toggle('fullscreen');
                            
                            if (document.fullscreenElement) {{
                                document.exitFullscreen();
                            }} else if (videoFeed.classList.contains('fullscreen')) {{
                                document.documentElement.requestFullscreen().catch(err => {{
                                    console.log(err);
                                }});
                            }}
                        }}

                        function updateControlsVisibility() {{
                            if (document.fullscreenElement) {{
                                controls.style.opacity = '0';
                            }} else {{
                                controls.style.opacity = '1';
                            }}
                        }}

                        function showControlsTemporarily() {{
                            if (document.fullscreenElement) {{
                                controls.style.opacity = '1';
                                clearTimeout(controlsTimeout);
                                controlsTimeout = setTimeout(() => {{
                                    controls.style.opacity = '0';
                                }}, 2000);
                            }}
                        }}

                        document.addEventListener('mousemove', showControlsTemporarily);
                        videoFeed.addEventListener('dblclick', toggleFullScreen);
                        document.addEventListener('fullscreenchange', () => {{
                            if (!document.fullscreenElement) {{
                                videoFeed.classList.remove('fullscreen');
                            }}
                            updateControlsVisibility();
                        }});
                    </script>
                </body>
                </html>
            '''.encode())
        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            
            try:
                while True:
                    ret, frame = self.server.video_source.read()
                    if not ret:
                        continue
                    
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
                    _, jpeg = cv2.imencode('.jpg', frame, encode_param)
                    
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Content-length', len(jpeg))
                    self.end_headers()
                    self.wfile.write(jpeg.tobytes())
                    self.wfile.write(b'\r\n')
            except Exception as e:
                print(f"Streaming error: {e}")
                pass

def list_video_sources():
    available_sources = []
    for i in range(10):
        info = get_camera_info(i)
        if info:
            available_sources.append(info)
    return available_sources

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def main():
    sources = list_video_sources()
    
    if not sources:
        print("No video sources found!")
        return
    
    print("\nAvailable video sources:")
    for i, source in enumerate(sources):
        print(f"{i}: {source['name']} ({source['resolution']}) - {source['backend']}")
    
    if len(sources) > 1:
        selected_idx = int(input("\nSelect video source number: "))
        selected_source = sources[selected_idx]
    else:
        selected_source = sources[0]
    
    print(f"\nUsing: {selected_source['name']}")
    
    local_ip = get_local_ip()
    port = 8000
    
    cap = cv2.VideoCapture(selected_source['id'])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    
    server = HTTPServer((local_ip, port), VideoStreamHandler)
    server.video_source = cap
    server.camera_info = selected_source
    
    print(f"\nStreaming video at: http://{local_ip}:{port}")
    print("Press Ctrl+C to stop the server")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        server.server_close()

if __name__ == "__main__":
    main()