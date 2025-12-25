#!/usr/bin/env python3
"""Simple MJPEG camera streaming server for Raspberry Pi

Uses rpicam-vid/libcamera-vid for capture and a simple HTTP server for streaming.

Usage:
  python3 tools/camera_server.py
  python3 tools/camera_server.py --port 8080 --width 640 --height 360
  python3 tools/camera_server.py --diagnose  # Check camera connection
"""

import argparse
import subprocess
import sys
import os
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler
import time


class MJPEGHTTPHandler(BaseHTTPRequestHandler):
    """Simple HTTP server for MJPEG streaming"""
    
    mjpeg_file = None
    mjpeg_pipe = None  # for USB camera via ffmpeg
    camera_error = None
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            if self.camera_error:
                html = f"""<!DOCTYPE html>
<html>
<head>
    <title>⚠ Camera Error</title>
    <meta charset="utf-8">
    <style>
        body {{ margin: 0; padding: 20px; background: #333; color: #fff; font-family: Arial; }}
        .error {{ background: #c00; padding: 20px; border-radius: 5px; }}
        h1 {{ color: #f44; }}
        code {{ background: #000; padding: 10px; display: block; margin: 10px 0; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>⚠ Camera Connection Error</h1>
    <div class="error">
        <p><strong>Error:</strong> {self.camera_error}</p>
        <h3>Troubleshooting:</h3>
        <ul>
            <li>Check camera is physically connected</li>
            <li>Enable camera: <code>sudo raspi-config</code> → Interface Options → Camera</li>
            <li>Verify camera: <code>rpicam-hello --list-cameras</code></li>
            <li>Restart Pi: <code>sudo reboot</code></li>
        </ul>
    </div>
</body>
</html>"""
            else:
                html = """<!DOCTYPE html>
<html>
<head>
    <title>Raspberry Pi Camera Stream</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            margin: 0; padding: 20px; background: #222; color: #fff;
            text-align: center; font-family: Arial, sans-serif;
        }
        .container { max-width: 900px; margin: 0 auto; }
        img { max-width: 100%; height: auto; border: 2px solid #555; margin-top: 20px; }
        .info { margin-top: 20px; color: #aaa; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎥 Raspberry Pi Camera Stream</h1>
        <img src="/stream.mjpg" alt="Camera Stream" onerror="this.src='/error.gif'" />
        <div class="info">
            <p>Auto-refreshing MJPEG stream</p>
            <p><a href="/stream.mjpg" target="_blank">Direct stream link</a></p>
        </div>
    </div>
</body>
</html>"""
            
            self.wfile.write(html.encode())
            
        elif self.path == '/stream.mjpg':
            # Serve proper multipart MJPEG with per-frame boundaries
            BOUNDARY = b'frame'
            self.send_response(200)
            self.send_header('Content-Type', f'multipart/x-mixed-replace; boundary={BOUNDARY.decode()}')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            def stream_from_reader(reader):
                buf = bytearray()
                try:
                    while True:
                        data = reader(4096)
                        if not data:
                            time.sleep(0.03)
                            continue
                        buf += data
                        # Find JPEG frames by SOI/EOI markers
                        while True:
                            soi = buf.find(b'\xff\xd8')
                            if soi < 0:
                                # Keep buffer reasonable
                                if len(buf) > 1_000_000:
                                    del buf[:-2]
                                break
                            eoi = buf.find(b'\xff\xd9', soi+2)
                            if eoi < 0:
                                # Need more data
                                # Trim head if needed
                                if soi > 0:
                                    del buf[:soi]
                                break
                            frame = bytes(buf[soi:eoi+2])
                            # Remove consumed bytes
                            del buf[:eoi+2]

                            # Write one multipart part
                            headers = (
                                b'--' + BOUNDARY + b'\r\n'
                                b'Content-Type: image/jpeg\r\n'
                                b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
                            )
                            self.wfile.write(headers)
                            self.wfile.write(frame)
                            self.wfile.write(b'\r\n')
                except BrokenPipeError:
                    return
                except Exception:
                    return

            # USB camera via ffmpeg pipe
            if self.mjpeg_pipe:
                stream_from_reader(self.mjpeg_pipe.read)
                return

            # RPi CSI camera via file tail
            if self.mjpeg_file and os.path.exists(self.mjpeg_file):
                try:
                    with open(self.mjpeg_file, 'rb') as f:
                        # Start at current end; new data will be appended by rpicam-vid
                        f.seek(0, os.SEEK_END)
                        def fread(n):
                            data = f.read(n)
                            if not data:
                                time.sleep(0.03)
                            return data
                        stream_from_reader(fread)
                        return
                except Exception:
                    pass

            # No source
            try:
                self.wfile.write(b'--' + BOUNDARY + b'\r\nContent-Type: text/plain\r\n\r\nNo stream source available.\r\n')
            except Exception:
                pass
        else:
            self.send_error(404, "Not Found")
    
    def log_message(self, format, *args):
        pass


def diagnose_camera():
    """Diagnose camera connection"""
    print("\n=== Camera Diagnostic ===\n")
    
    # Check rpicam tools
    print("1. Checking rpicam tools...")
    try:
        result = subprocess.run(['rpicam-hello', '--list-cameras'], 
                              capture_output=True, text=True, timeout=5)
        print(f"   Output: {result.stdout.strip()}")
        if result.returncode != 0:
            print(f"   Error: {result.stderr.strip()}")
    except FileNotFoundError:
        print("   ✗ rpicam-hello not found")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Check camera devices
    print("\n2. Checking /dev/video* devices...")
    video_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
    if video_devices:
        print(f"   ✓ Found: {', '.join(video_devices)}")
    else:
        print("   ✗ No /dev/video* devices found")
    
    # Check raspi-config camera setting
    print("\n3. Camera must be enabled in raspi-config")
    print("   Run: sudo raspi-config")
    print("   Go to: Interface Options > Camera > Enable")
    
    print("\n4. If camera was recently enabled, restart with:")
    print("   sudo reboot\n")


def start_usb_camera_server(device: str, port: int = 8080, width: int = 640, height: int = 360, fps: int = 30):
    """Start USB camera streaming via ffmpeg piping MJPEG to HTTP server"""
    print(f"\n🎥 Starting USB Camera Streaming Server")
    print(f"   Device: {device}, Port: {port}, Resolution: {width}x{height}, FPS: {fps}\n")

    # ffmpeg command to read from V4L2 and output MJPEG to stdout
    cmd = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel', 'error',
        '-f', 'v4l2',
        '-video_size', f'{width}x{height}',
        '-framerate', str(fps),
        '-i', device,
        '-f', 'mjpeg',
        '-'
    ]

    try:
        print(f"Trying ffmpeg...", end=' ', flush=True)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1)
        if process.poll() is not None:
            _, err = process.communicate(timeout=1)
            msg = err.decode().strip()[:300]
            print(f"✗ ({msg})")
            raise RuntimeError(f"ffmpeg exited: {msg}")
        print("✓")

        # Bind pipe to handler and start HTTP server
        MJPEGHTTPHandler.mjpeg_pipe = process.stdout
        MJPEGHTTPHandler.camera_error = None

        server = HTTPServer(('0.0.0.0', port), MJPEGHTTPHandler)
        print(f"✓ HTTP server listening on port {port}")
        print(f"✓ Open browser at: http://localhost:{port}/")
        print("\nPress Ctrl+C to stop...\n")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
    except FileNotFoundError:
        print("✗ ffmpeg not found. Install with: sudo apt install -y ffmpeg")
        sys.exit(1)
    except Exception as e:
        print(f"✗ USB camera streaming error: {e}")
        sys.exit(1)


def start_rpi_camera_server(port=8080, width=640, height=360, fps=30):
    """Start RPi camera streaming"""
    print(f"\n🎥 Starting Raspberry Pi Camera Streaming Server")
    print(f"   Port: {port}, Resolution: {width}x{height}, FPS: {fps}\n")
    
    mjpeg_file = f"/tmp/rpi_camera_{port}.mjpg"
    camera_error = None
    
    # Try rpicam-vid first
    commands = [
        {
            'name': 'rpicam-vid',
            'cmd': [
                'rpicam-vid',
                '--width', str(width),
                '--height', str(height),
                '--framerate', str(fps),
                '--codec', 'mjpeg',
                '--nopreview',
                '-n',
                '-t', '0',  # Infinite timeout
                '--output', mjpeg_file
            ]
        },
        {
            'name': 'libcamera-vid',
            'cmd': [
                'libcamera-vid',
                '--width', str(width),
                '--height', str(height),
                '--framerate', str(fps),
                '--codec', 'mjpeg',
                '--output', mjpeg_file,
                '-t', '0'
            ]
        }
    ]
    
    camera_process = None
    
    for cmd_info in commands:
        cmd_name = cmd_info['name']
        cmd = cmd_info['cmd']
        
        try:
            print(f"Trying {cmd_name}...", end=' ', flush=True)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait to see if process starts successfully
            time.sleep(2)
            
            if process.poll() is None:  # Process still running
                print("✓")
                camera_process = process
                print(f"✓ Camera initialized with {cmd_name}\n")
                break
            else:
                # Process exited, get error
                _, stderr = process.communicate(timeout=1)
                camera_error = stderr.decode().strip()[:200]
                print(f"✗ ({camera_error})")
                
        except FileNotFoundError:
            print(f"✗ (not found)")
            camera_error = f"{cmd_name} not installed"
        except subprocess.TimeoutExpired:
            process.kill()
            print("✗ (timeout)")
            camera_error = "Process timeout"
        except Exception as e:
            print(f"✗ ({e})")
            camera_error = str(e)
    
    if camera_process is None:
        print("\n" + "="*60)
        print("ERROR: Camera not accessible!")
        print("="*60)
        print(f"\nLast error: {camera_error}\n")
        print("Common causes:")
        print("  1. No camera connected to CSI/DSI port")
        print("  2. Camera not enabled in raspi-config")
        print("  3. Camera drivers not loaded")
        print("\nFix:")
        print("  1. sudo raspi-config")
        print("  2. Interface Options → Camera → Enable")
        print("  3. sudo reboot")
        print("")
        camera_error = "Camera not found. Check physical connection and enable in raspi-config."
    
    # Set up HTTP server
    MJPEGHTTPHandler.mjpeg_file = mjpeg_file
    MJPEGHTTPHandler.camera_error = camera_error
    
    try:
        server = HTTPServer(('0.0.0.0', port), MJPEGHTTPHandler)
        print(f"✓ HTTP server listening on port {port}")
        print(f"✓ Open browser at: http://localhost:{port}/")
        print(f"\nPress Ctrl+C to stop...\n")
        
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        if camera_process:
            camera_process.terminate()
            try:
                camera_process.wait(timeout=2)
            except:
                camera_process.kill()
        if os.path.exists(mjpeg_file):
            os.remove(mjpeg_file)
        print("Stopped.")


def main():
    parser = argparse.ArgumentParser(
        description='Raspberry Pi/USB camera MJPEG streaming server',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--type', choices=['rpi', 'usb'], default='rpi',
                        help='Camera type: rpi (CSI/libcamera) or usb (V4L2)')
    parser.add_argument('--device', type=str, default='/dev/video0',
                        help='USB camera device path (default: /dev/video0)')
    parser.add_argument('--port', type=int, default=8080,
                        help='HTTP port (default: 8080)')
    parser.add_argument('--width', type=int, default=640,
                        help='Frame width (default: 640)')
    parser.add_argument('--height', type=int, default=360,
                        help='Frame height (default: 360)')
    parser.add_argument('--fps', type=int, default=30,
                        help='Frames per second (default: 30)')
    parser.add_argument('--diagnose', action='store_true',
                        help='Run camera diagnostic and exit')
    
    args = parser.parse_args()
    
    if args.diagnose:
        diagnose_camera()
        return
    
    try:
        if args.type == 'usb':
            start_usb_camera_server(args.device, args.port, args.width, args.height, args.fps)
        else:
            start_rpi_camera_server(args.port, args.width, args.height, args.fps)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
