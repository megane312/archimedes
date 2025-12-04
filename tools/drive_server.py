"""Drive server

Run on Raspberry Pi. Listens for UDP JSON commands and applies them to RobotDrive.

Simple protocol (JSON messages):
- hat: {"type":"hat","value":[x,y]}  where x,y are integers (-1/0/1)
- axes: {"type":"axes","a7":-1|0|1,"a8":-1|0|1}
- raw: {"type":"raw","m1_dir":true,"m1_duty":100,"m2_dir":false,"m2_duty":100}
- stop: {"type":"stop"}

Run on Pi:
  sudo PYTHONPATH=. python3 tools/drive_server.py --bind 0.0.0.0 --port 5005

"""
import argparse
import json
import socket
import time
from robot_drive import default_motor_map, Motor, RobotDrive, compute_motor_commands, compute_motor_commands_from_hat


def handle_message(rd: RobotDrive, data: dict):
    t = data.get('type')
    try:
        if t == 'hat':
            hat = tuple(data.get('value', (0, 0)))
            (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands_from_hat(hat)
        elif t == 'axes':
            a7 = int(data.get('a7', 0))
            a8 = int(data.get('a8', 0))
            (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands(a7, a8)
        elif t == 'raw':
            m1_dir = bool(data.get('m1_dir', True))
            m1_duty = int(data.get('m1_duty', 0))
            m2_dir = bool(data.get('m2_dir', True))
            m2_duty = int(data.get('m2_duty', 0))
        elif t == 'stop':
            rd.set_motor(0, True, 0)
            rd.set_motor(1, True, 0)
            return
        else:
            # unknown; ignore
            return

        rd.set_motor(0, m1_dir, m1_duty)
        rd.set_motor(1, m2_dir, m2_duty)
    except Exception as e:
        print('Error applying command:', e)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bind', default='0.0.0.0', help='Bind address')
    p.add_argument('--port', type=int, default=5005, help='UDP port to listen on')
    p.add_argument('--invert-dir', action='store_true', help='Invert DIR polarity')
    args = p.parse_args()

    motor_pairs = default_motor_map()
    motors = [Motor(d, p) for d, p in motor_pairs]
    rd = RobotDrive(motors, invert_dir=args.invert_dir)
    rd.setup_all()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    sock.settimeout(1.0)

    print(f'Drive server listening on {args.bind}:{args.port} (UDP)')
    try:
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception as e:
                print('Socket error:', e)
                continue

            try:
                msg = json.loads(data.decode('utf-8'))
            except Exception as e:
                print('Invalid JSON from', addr, e)
                continue

            print(time.strftime('%H:%M:%S'), 'msg from', addr, msg)
            handle_message(rd, msg)
    except KeyboardInterrupt:
        print('Server stopped by user')
    finally:
        rd.stop_all()
        sock.close()


if __name__ == '__main__':
    main()
