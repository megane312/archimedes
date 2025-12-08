#!/usr/bin/env python3
"""Drive HTTP client

Polls a notebook-PC HTTP server (`GET /state`) and applies the returned
controller state to the local motors via `RobotDrive`.

Also provides simple direct commands to spin motors for quick manual tests.

Usage (polling):
  sudo PYTHONPATH=. python3 tools/drive_http_client.py --url http://PC:8000/state --interval 0.1

Direct test (spin motor 0 forward 100% for 2s):
  sudo PYTHONPATH=. python3 tools/drive_http_client.py --spin "0:forward:100:2"

The script uses the same Motor/RobotDrive implementation as `robot_drive.py`.
"""
import argparse
import json
import time
import urllib.request
from typing import Optional

from robot_drive import default_motor_map, Motor, RobotDrive, compute_motor_commands, compute_motor_commands_from_hat


def fetch_json(url: str, timeout: float = 1.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read()
            return json.loads(data.decode('utf-8'))
    except Exception:
        return None


def apply_msg(rd: RobotDrive, msg: Optional[dict], debug: bool = False, axis7_idx: int = 7, axis8_idx: int = 8):
    """Apply message to RobotDrive. Returns True if any motor commands were applied.

    Supports two message shapes:
    - explicit command objects with 'type' (hat / axes / raw / stop)
    - joystick snapshot returned by `joy_server` (`{'joysticks': [...]}`)

    When given a joystick snapshot, the first joystick is used; hats take
    priority if present, otherwise axes at indices `axis7_idx`/`axis8_idx`
    are quantized to -1/0/1 and passed to `compute_motor_commands`.
    """
    if msg is None:
        if debug:
            print(time.strftime('%H:%M:%S'), 'fetch returned None (network or parse error)')
        return False

    # Handle joystick snapshot produced by tools/joy_server.py
    if isinstance(msg, dict) and 'joysticks' in msg:
        try:
            js = msg.get('joysticks') or []
            if not js:
                if debug:
                    print(time.strftime('%H:%M:%S'), 'joystick snapshot empty')
                return False
            j0 = js[0]
            # hats first (D-pad)
            hats = j0.get('hats', [])
            if hats and len(hats) > 0:
                hat = tuple(hats[0])
                (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands_from_hat(hat)
                source = f'hat {hat}'
            else:
                axes = j0.get('axes', [])

                def quant(v):
                    try:
                        if v > 0.5:
                            return 1
                        if v < -0.5:
                            return -1
                    except Exception:
                        pass
                    return 0

                a7 = 0
                a8 = 0
                if 0 <= axis7_idx < len(axes):
                    a7 = quant(axes[axis7_idx])
                if 0 <= axis8_idx < len(axes):
                    a8 = quant(axes[axis8_idx])

                (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands(a7, a8)
                source = f'axes a7={a7} a8={a8}'

            if debug:
                print(time.strftime('%H:%M:%S'), 'applying joystick snapshot ->', source, '->', "m1:", (m1_dir, m1_duty), "m2:", (m2_dir, m2_duty))

            rd.set_motor(0, m1_dir, m1_duty)
            rd.set_motor(1, m2_dir, m2_duty)
            return True
        except Exception as e:
            if debug:
                print(time.strftime('%H:%M:%S'), 'error applying joystick snapshot:', e)
            return False

    # Fallback: explicit command messages with 'type' field
    t = msg.get('type')
    try:
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
            if debug:
                print(time.strftime('%H:%M:%S'), 'received stop command')
            rd.set_motor(0, True, 0)
            rd.set_motor(1, True, 0)
            return True
        else:
            if debug:
                print(time.strftime('%H:%M:%S'), 'unknown message type:', t)
            return False

        if debug:
            print(time.strftime('%H:%M:%S'), 'applying', t, '->', "m1:", (m1_dir, m1_duty), "m2:", (m2_dir, m2_duty))

        rd.set_motor(0, m1_dir, m1_duty)
        rd.set_motor(1, m2_dir, m2_duty)
        return True
    except Exception as e:
        print('Error applying command:', e)
        return False


def parse_spin_arg(s: str):
    """Parse spin argument formatted as: idx:forward|reverse:duty:duration
    Example: "0:forward:100:2" -> (0, True, 100, 2.0)
    """
    try:
        idx_s, dir_s, duty_s, dur_s = s.split(':')
        idx = int(idx_s)
        direction = True if dir_s.lower() in ('f', 'forward', '1', 'true') else False
        duty = int(duty_s)
        dur = float(dur_s)
        return idx, direction, max(0, min(100, duty)), max(0.0, dur)
    except Exception:
        raise ValueError('Invalid --spin format. Use idx:forward|reverse:duty:duration')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', help='URL to poll (e.g. http://PC:8000/state)')
    p.add_argument('--interval', type=float, default=0.1, help='Poll interval (s)')
    p.add_argument('--invert-dir', action='store_true', help='Invert DIR polarity')
    p.add_argument('--debug', action='store_true', help='Enable debug logging (prints fetch failures and apply actions)')
    p.add_argument('--spin', help='Manual spin: "idx:forward|reverse:duty:duration"')
    p.add_argument('--spin-all', help='Spin all motors: "forward|reverse:duty:duration"')
    p.add_argument('--axis7', type=int, default=7, help='Index of axis to treat as axis7 when using joystick snapshots')
    p.add_argument('--axis8', type=int, default=8, help='Index of axis to treat as axis8 when using joystick snapshots')
    args = p.parse_args()

    motor_pairs = default_motor_map()
    motors = [Motor(d, p) for d, p in motor_pairs]
    rd = RobotDrive(motors, invert_dir=args.invert_dir)
    rd.setup_all()

    try:
        # direct spin mode (one-shot)
        if args.spin:
            idx, direction, duty, dur = parse_spin_arg(args.spin)
            if not (0 <= idx < len(motors)):
                print('Invalid motor index')
                return
            print(f'Spin motor {idx} dir={"F" if direction else "R"} duty={duty}% for {dur}s')
            rd.set_motor(idx, direction, duty)
            time.sleep(dur)
            rd.set_motor(idx, True, 0)
            return

        if args.spin_all:
            try:
                dir_s, duty_s, dur_s = args.spin_all.split(':')
                direction = True if dir_s.lower() in ('f', 'forward', '1', 'true') else False
                duty = int(duty_s)
                dur = float(dur_s)
            except Exception:
                print('Invalid --spin-all format. Use forward|reverse:duty:duration')
                return
            print(f'Spin all motors dir={"F" if direction else "R"} duty={duty}% for {dur}s')
            rd.set_all(direction, duty)
            time.sleep(dur)
            rd.stop_all()
            return

        # polling mode
        if not args.url:
            print('No action specified. Use --url to poll or --spin/--spin-all to test.')
            return

        print('Drive HTTP client polling', args.url)
        prev = None
        while True:
            msg = fetch_json(args.url, timeout=args.interval)
            if msg is not None:
                # print only on change to reduce spam
                if msg != prev:
                    print(time.strftime('%H:%M:%S'), 'fetched', msg)
                    prev = msg
            applied = apply_msg(rd, msg, debug=args.debug, axis7_idx=args.axis7, axis8_idx=args.axis8)
            if args.debug and not applied:
                print(time.strftime('%H:%M:%S'), 'no command applied for fetched message')
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('Client stopped by user')
    finally:
        rd.stop_all()


if __name__ == '__main__':
    main()
