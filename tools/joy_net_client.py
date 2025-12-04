"""Joystick network client

Run on the laptop with a controller attached. Reads joystick (pygame) and sends
JSON messages to the Pi server (UDP).

Example:
  PYTHONPATH=. python3 tools/joy_net_client.py --host 192.168.1.10 --port 5005 --interval 0.1

Sends 'hat' messages if hat present, otherwise sends 'axes' with quantized a7/a8.
"""
import time
import argparse
import socket
import json

try:
    import pygame
except Exception:
    pygame = None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', required=True, help='Pi host IP')
    p.add_argument('--port', type=int, default=5005, help='Pi UDP port')
    p.add_argument('--interval', type=float, default=0.1, help='Poll interval (s)')
    p.add_argument('--axis7', type=int, default=7)
    p.add_argument('--axis8', type=int, default=8)
    args = p.parse_args()

    if pygame is None:
        print('pygame not installed. Install with: pip3 install pygame')
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server = (args.host, args.port)

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print('No joystick found. Connect controller and try again.')
        return

    joy = pygame.joystick.Joystick(0)
    joy.init()
    print('Using joystick:', joy.get_name())

    prev = None
    try:
        while True:
            pygame.event.pump()
            hat_val = None
            if joy.get_numhats() > 0:
                hat_val = joy.get_hat(0)

            if hat_val is not None and hat_val != (0, 0):
                msg = {'type': 'hat', 'value': [int(hat_val[0]), int(hat_val[1])]}
            else:
                # quantize axes
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

                a7 = read_axis(args.axis7)
                a8 = read_axis(args.axis8)
                msg = {'type': 'axes', 'a7': a7, 'a8': a8}

            if msg != prev:
                data = json.dumps(msg).encode('utf-8')
                sock.sendto(data, server)
                prev = msg
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('Client stopped')
    finally:
        sock.close()
        try:
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
