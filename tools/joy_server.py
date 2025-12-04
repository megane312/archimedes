"""Joystick HTTP server

Run on the laptop. Reads controller input with pygame and serves the latest
state via a simple HTTP GET endpoint `/state` (JSON).

Usage:
  PYTHONPATH=. python3 tools/joy_server.py --host 0.0.0.0 --port 8000

The server runs two threads:
- joystick thread: polls pygame and updates latest state
- HTTP server thread: responds to GET /state with JSON command

Returned JSON format matches the drive server protocol, e.g.:
  {"type":"hat","value":[0,1]}
  {"type":"axes","a7":1,"a8":0}

No external web framework required.
"""
import argparse
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import pygame
except Exception:
    pygame = None

LATEST = {'msg': {'type': 'axes', 'a7': 0, 'a8': 0}}
LOCK = threading.Lock()


def joystick_loop(axis7=7, axis8=8, poll=0.05):
    global LATEST
    if pygame is None:
        print('pygame not installed. Install with: pip3 install pygame')
        return

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print('No joystick found. Connect controller and try again.')
        return

    joy = pygame.joystick.Joystick(0)
    joy.init()
    print('Joystick server using:', joy.get_name())

    try:
        while True:
            pygame.event.pump()
            hat_val = None
            if joy.get_numhats() > 0:
                hat_val = joy.get_hat(0)

            if hat_val is not None and hat_val != (0, 0):
                msg = {'type': 'hat', 'value': [int(hat_val[0]), int(hat_val[1])]}
            else:
                def read_axis(idx: int) -> int:
                    try:
                        v = joy.get_axis(idx)
                    except Exception:
                        return 0
                    if v > 0.5:
                        return 1
                    if v < -0.5:
                        return -1
                    return 0

                a7 = read_axis(axis7)
                a8 = read_axis(axis8)
                msg = {'type': 'axes', 'a7': a7, 'a8': a8}

            with LOCK:
                LATEST['msg'] = msg
            time.sleep(poll)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass


class StateHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/state':
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')
            return

        with LOCK:
            msg = LATEST.get('msg', {'type': 'axes', 'a7': 0, 'a8': 0})
        data = json.dumps(msg).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # silence default logging
        return


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--axis7', type=int, default=7)
    p.add_argument('--axis8', type=int, default=8)
    args = p.parse_args()

    t = threading.Thread(target=joystick_loop, args=(args.axis7, args.axis8), daemon=True)
    t.start()

    server = HTTPServer((args.host, args.port), StateHandler)
    print(f'Joystick HTTP server listening on {args.host}:{args.port} (GET /state)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Server stopped')
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
