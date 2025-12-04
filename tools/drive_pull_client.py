"""Drive pull client

Run on Raspberry Pi. Periodically polls a notebook-PC HTTP server for the
latest controller state and applies it to local motors via RobotDrive.

Usage:
  sudo PYTHONPATH=. python3 tools/drive_pull_client.py --url http://192.168.1.50:8000/state --interval 0.1

The server is expected to return JSON in the same format as other tools:
- {"type":"hat","value":[x,y]}
- {"type":"axes","a7":-1|0|1,"a8":-1|0|1}
- {"type":"raw", ...}
- {"type":"stop"}

"""
import argparse
import json
import time
import urllib.request

from robot_drive import default_motor_map, Motor, RobotDrive, compute_motor_commands, compute_motor_commands_from_hat


def fetch_json(url, timeout=1.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read()
            return json.loads(data.decode('utf-8'))
    except Exception as e:
        # network or parse error
        return None


def apply_msg(rd, msg):
    if msg is None:
        return
    t = msg.get('type')
    if t == 'hat':
        hat = tuple(msg.get('value', (0, 0)))
        (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands_from_hat(hat)
    elif t == 'axes':
        a7 = int(msg.get('a7', 0))
        a8 = int(msg.get('a8', 0))
        (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands(a7, a8)
    elif t == 'raw':
        m1_dir = bool(msg.get('m1_dir', True))
        m1_duty = int(msg.get('m1_duty', 0))
        m2_dir = bool(msg.get('m2_dir', True))
        m2_duty = int(msg.get('m2_duty', 0))
    elif t == 'stop':
        rd.set_motor(0, True, 0)
        rd.set_motor(1, True, 0)
        return
    else:
        return

    rd.set_motor(0, m1_dir, m1_duty)
    rd.set_motor(1, m2_dir, m2_duty)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', required=True, help='URL to poll (e.g. http://HOST:PORT/state)')
    p.add_argument('--interval', type=float, default=0.1, help='Poll interval (s)')
    p.add_argument('--invert-dir', action='store_true', help='Invert DIR polarity')
    args = p.parse_args()

    motor_pairs = default_motor_map()
    motors = [Motor(d, p) for d, p in motor_pairs]
    rd = RobotDrive(motors, invert_dir=args.invert_dir)
    rd.setup_all()

    print('Drive pull client polling', args.url)
    try:
        while True:
            msg = fetch_json(args.url, timeout=args.interval)
            if msg is not None:
                print(time.strftime('%H:%M:%S'), 'fetched', msg)
            apply_msg(rd, msg)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('Client stopped by user')
    finally:
        rd.stop_all()


if __name__ == '__main__':
    main()
