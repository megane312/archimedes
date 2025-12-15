#!/usr/bin/env python3
"""Drive HTTP client

Polls a notebook-PC HTTP server (`GET /state`) and applies the returned
controller state to the local motors via `RobotDrive`.

Supports both 2-motor and 4-motor control modes.

For 2-motor mode (default):
  - Motor 0: controlled by axis 7 (left/forward)
  - Motor 1: controlled by axis 8 (right/reverse)

For 4-motor mode (custom mapping):
      - Motor 0/1 are driven by D-pad hats:
          * (0,  1): m0 F100, m1 R100 (forward)
          * (0, -1): m0 R100, m1 F100 (backward)
          * (-1, 0): m0 F100, m1 R50  (turn left)
          * (1,  0): m0 F50,  m1 R100 (turn right)
      - buttons[4]==1 with hats (0,1)/(0,-1): stair up/down (same hat mapping) + motor2 F/R100
      - buttons[0]==1: motor3 R100 / buttons[3]==1: motor3 F100
      - Motors 2/3 otherwise stay stopped unless buttons trigger them

Also provides simple direct commands to spin motors for quick manual tests.

Usage (polling, 2-motor mode):
  sudo PYTHONPATH=. python3 tools/drive_http_client.py --url http://PC:8000/state --interval 0.1

Usage (polling, 4-motor mode):
  sudo PYTHONPATH=. python3 tools/drive_http_client.py --url http://PC:8000/state --motors 4 --interval 0.1

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


def compute_motor_commands_4motors(a7: int, a8: int):
    """Compute commands for 4 motors from two analog axes.
    
    Motor mapping (tank drive with 4 motors):
    - Motors 0,1: left side (controlled by axis a7)
    - Motors 2,3: right side (controlled by axis a8)
    
    Returns tuple of 4 motor commands: ((m0_dir, m0_duty), (m1_dir, m1_duty), (m2_dir, m2_duty), (m3_dir, m3_duty))
    """
    # Left motors (0, 1) - controlled by a7
    if a7 > 0:
        m0_dir, m0_duty = True, min(100, abs(a7) * 50)
        m1_dir, m1_duty = True, min(100, abs(a7) * 50)
    elif a7 < 0:
        m0_dir, m0_duty = False, min(100, abs(a7) * 50)
        m1_dir, m1_duty = False, min(100, abs(a7) * 50)
    else:
        m0_dir, m0_duty = True, 0
        m1_dir, m1_duty = True, 0
    
    # Right motors (2, 3) - controlled by a8
    if a8 > 0:
        m2_dir, m2_duty = True, min(100, abs(a8) * 50)
        m3_dir, m3_duty = True, min(100, abs(a8) * 50)
    elif a8 < 0:
        m2_dir, m2_duty = False, min(100, abs(a8) * 50)
        m3_dir, m3_duty = False, min(100, abs(a8) * 50)
    else:
        m2_dir, m2_duty = True, 0
        m3_dir, m3_duty = True, 0
    
    return ((m0_dir, m0_duty), (m1_dir, m1_duty), (m2_dir, m2_duty), (m3_dir, m3_duty))


def compute_motor_commands_4motors_from_hat(hat):
    """Compute commands for 4 motors from D-pad hat (custom mapping).

    Only motors 0/1 are driven by the hat; motors 2/3 stay stopped here.
    (Motor2 may be driven separately by button4 overrides.)
    """
    hx, hy = hat

    if hy > 0:  # Up / forward
        return ((True, 100), (False, 100), (True, 0), (True, 0))
    if hy < 0:  # Down / backward
        return ((False, 100), (True, 100), (True, 0), (True, 0))
    if hx < 0:  # Left turn
        return ((True, 100), (False, 50), (True, 0), (True, 0))
    if hx > 0:  # Right turn
        return ((True, 50), (False, 100), (True, 0), (True, 0))
    # Neutral
    return ((True, 0), (True, 0), (True, 0), (True, 0))


def apply_msg(rd: RobotDrive, msg: Optional[dict], debug: bool = False, axis7_idx: int = 7, axis8_idx: int = 8, num_motors: int = 2):
    """Apply message to RobotDrive. Returns True if any motor commands were applied.

    Supports two message shapes:
    - explicit command objects with 'type' (hat / axes / raw / stop)
    - joystick snapshot returned by `joy_server` (`{'joysticks': [...]}`)

    When given a joystick snapshot, the first joystick is used; hats take
    priority if present, otherwise axes at indices `axis7_idx`/`axis8_idx`
    are quantized to -1/0/1 and passed to the appropriate motor command function.
    
    num_motors: 2 for 2-motor control, 4 for 4-motor control
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
            buttons = j0.get('buttons', [])
            hat = None
            if hats and len(hats) > 0:
                hat = tuple(hats[0])
                if num_motors == 4:
                    commands = compute_motor_commands_4motors_from_hat(hat)
                else:
                    (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands_from_hat(hat)
                    commands = ((m1_dir, m1_duty), (m2_dir, m2_duty))
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

                if num_motors == 4:
                    commands = compute_motor_commands_4motors(a7, a8)
                else:
                    (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands(a7, a8)
                    commands = ((m1_dir, m1_duty), (m2_dir, m2_duty))
                source = f'axes a7={a7} a8={a8}'

            # Apply button-based overrides for 4-motor mode
            if num_motors == 4:
                cmd_list = list(commands)

                # Ensure 4 entries
                while len(cmd_list) < 4:
                    cmd_list.append((True, 0))

                # Button 4 + specific hat directions (stair up/down): add motor2 drive
                if len(buttons) > 4 and buttons[4] == 1 and hat in ((0, 1), (0, -1)):
                    # reuse hat mapping for m0/m1, and drive m2 with same direction as m0
                    stair_cmds = list(compute_motor_commands_4motors_from_hat(hat))
                    cmd_list[0] = stair_cmds[0]
                    cmd_list[1] = stair_cmds[1]
                    # m2 follows m0 direction/duty for stair assist
                    m0_dir, m0_duty = stair_cmds[0]
                    cmd_list[2] = (m0_dir, 100)

                # Motor3 control via buttons: button0 reverse, button3 forward
                # Priority: if both pressed, Button 0 (reverse) wins
                b0 = (len(buttons) > 0 and buttons[0] == 1)
                b3 = (len(buttons) > 3 and buttons[3] == 1)
                if b0 or b3:
                    cmd_list[3] = ((False, 100) if b0 else (True, 100))

                commands = tuple(cmd_list)

            if debug:
                print(time.strftime('%H:%M:%S'), 'applying joystick snapshot ->', source, '->', f'motors: {commands}')

            for i, (m_dir, m_duty) in enumerate(commands):
                rd.set_motor(i, m_dir, m_duty)
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
            if num_motors == 4:
                commands = compute_motor_commands_4motors_from_hat(hat)
            else:
                (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands_from_hat(hat)
                commands = ((m1_dir, m1_duty), (m2_dir, m2_duty))
        elif t == 'axes':
            a7 = int(msg.get('a7', 0))
            a8 = int(msg.get('a8', 0))
            if num_motors == 4:
                commands = compute_motor_commands_4motors(a7, a8)
            else:
                (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands(a7, a8)
                commands = ((m1_dir, m1_duty), (m2_dir, m2_duty))
        elif t == 'raw':
            if num_motors == 4:
                m0_dir = bool(msg.get('m0_dir', True))
                m0_duty = int(msg.get('m0_duty', 0))
                m1_dir = bool(msg.get('m1_dir', True))
                m1_duty = int(msg.get('m1_duty', 0))
                m2_dir = bool(msg.get('m2_dir', True))
                m2_duty = int(msg.get('m2_duty', 0))
                m3_dir = bool(msg.get('m3_dir', True))
                m3_duty = int(msg.get('m3_duty', 0))
                commands = ((m0_dir, m0_duty), (m1_dir, m1_duty), (m2_dir, m2_duty), (m3_dir, m3_duty))
            else:
                m1_dir = bool(msg.get('m1_dir', True))
                m1_duty = int(msg.get('m1_duty', 0))
                m2_dir = bool(msg.get('m2_dir', True))
                m2_duty = int(msg.get('m2_duty', 0))
                commands = ((m1_dir, m1_duty), (m2_dir, m2_duty))
        elif t == 'stop':
            if debug:
                print(time.strftime('%H:%M:%S'), 'received stop command')
            for i in range(num_motors):
                rd.set_motor(i, True, 0)
            return True
        else:
            if debug:
                print(time.strftime('%H:%M:%S'), 'unknown message type:', t)
            return False

        if debug:
            print(time.strftime('%H:%M:%S'), 'applying', t, '->', f'motors: {commands}')

        for i, (m_dir, m_duty) in enumerate(commands):
            rd.set_motor(i, m_dir, m_duty)
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
    p.add_argument('--motors', type=int, choices=[2, 4], default=2, help='Number of motors to control (2 or 4)')
    args = p.parse_args()

    motor_pairs = default_motor_map()
    # Use only the first num_motors pairs
    motor_pairs = motor_pairs[:args.motors]
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

        print(f'Drive HTTP client polling {args.url} (controlling {args.motors} motors)')
        prev = None
        while True:
            msg = fetch_json(args.url, timeout=args.interval)
            if msg is not None:
                # print only on change to reduce spam
                if msg != prev:
                    print(time.strftime('%H:%M:%S'), 'fetched', msg)
                    prev = msg
            applied = apply_msg(rd, msg, debug=args.debug, axis7_idx=args.axis7, axis8_idx=args.axis8, num_motors=args.motors)
            if args.debug and not applied:
                print(time.strftime('%H:%M:%S'), 'no command applied for fetched message')
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('Client stopped by user')
    finally:
        rd.stop_all()


if __name__ == '__main__':
    main()
