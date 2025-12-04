"""
robot_drive.py

4つのMD10CモータードライバをRaspberry Piから制御するための簡易ライブラリ/デモプログラム。

設計方針:
- 既存の `sample.py` が提供する GPIO バックエンド選択（pigpio/RPi.GPIO/libgpiod/sysfs/fake）を再利用します。
- 各モーターは DIR ピン（方向）と PWM ピン（パルス幅）を持ち、ソフト/ハード PWM を使用して回転速度を制御します。
- コマンドライン引数でデモ実行や一括制御が可能です。

注意: 実機では `sudo` で実行してください。
"""

import time
import argparse
from typing import List, Tuple

# optional pygame for controller input
try:
    import pygame
    _HAS_PYGAME = True
except Exception:
    pygame = None
    _HAS_PYGAME = False

# Reuse GPIO/backends from sample.py
import sample as gpio_mod


class Motor:
    def __init__(self, dir_pin: int, pwm_pin: int, freq: int = 1000):
        self.dir_pin = dir_pin
        self.pwm_pin = pwm_pin
        self.freq = freq
        self._pwm = None

    def setup(self, gpio):
        gpio.setmode(gpio.BCM)
        gpio.setup(self.dir_pin, gpio.OUT)
        gpio.setup(self.pwm_pin, gpio.OUT)
        self._pwm = gpio.PWM(self.pwm_pin, self.freq)
        self._pwm.start(0)

    def set_speed(self, gpio, direction: bool, duty: int):
        # direction: True = forward/high on DIR pin, False = reverse/low
        gpio.output(self.dir_pin, gpio.HIGH if direction else gpio.LOW)
        if self._pwm is not None:
            duty = max(0, min(100, duty))
            self._pwm.ChangeDutyCycle(duty)
        # debug log for hardware observation
        try:
            print(f"[MOTOR] DIR_pin={self.dir_pin} PWM_pin={self.pwm_pin} -> direction={'F' if direction else 'R'} duty={duty}")
        except Exception:
            pass

    def stop(self):
        try:
            if self._pwm is not None:
                self._pwm.ChangeDutyCycle(0)
        except Exception:
            pass
        try:
            print(f"[MOTOR] stop DIR_pin={self.dir_pin} PWM_pin={self.pwm_pin}")
        except Exception:
            pass


class RobotDrive:
    def __init__(self, motors: List[Motor], invert_dir: bool = False):
        self.motors = motors
        self.gpio = gpio_mod.GPIO
        self.invert_dir = invert_dir

    def setup_all(self):
        for m in self.motors:
            m.setup(self.gpio)

    def stop_all(self):
        for m in self.motors:
            m.stop()
        try:
            self.gpio.cleanup()
        except Exception:
            pass

    def set_motor(self, idx: int, direction: bool, duty: int):
        if not (0 <= idx < len(self.motors)):
            raise IndexError('motor index out of range')
        # apply global inversion if configured
        eff_dir = (not direction) if getattr(self, 'invert_dir', False) else direction
        self.motors[idx].set_speed(self.gpio, eff_dir, duty)

    def set_all(self, direction: bool, duty: int):
        for i in range(len(self.motors)):
            self.set_motor(i, direction, duty)

    def demo_sequence(self, duration: float = 1.0):
        # simple sequential demo: spin each motor forward then stop
        try:
            for i in range(len(self.motors)):
                print(f"Motor {i+1} forward 50%")
                self.set_motor(i, True, 50)
                time.sleep(duration)
                print(f"Motor {i+1} stop")
                self.set_motor(i, True, 0)
                time.sleep(0.2)

            # all motors reverse briefly
            print("All motors reverse 40% for 1s")
            self.set_all(False, 40)
            time.sleep(1.0)
            self.set_all(True, 0)
        finally:
            self.stop_all()


def default_motor_map() -> List[Tuple[int, int]]:
    # Default BCM pin mapping for 4 motors: (DIR, PWM)
    # You can override these via command line arguments or modify this function.
    return [
        (17, 18),  # Motor 1 (existing sample default)
        (22, 23),  # Motor 2
        (24, 25),  # Motor 3
        (27, 12),  # Motor 4
    ]


def parse_args():
    p = argparse.ArgumentParser(description='RobotDrive control for 4 MD10C motors')
    p.add_argument('--demo', action='store_true', help='Run the demo sequence')
    p.add_argument('--duration', type=float, default=1.0, help='Duration for each demo step (seconds)')
    p.add_argument('--all-duty', type=int, default=None, help='Set all motors to this duty (0-100) and exit')
    p.add_argument('--all-dir', choices=['forward', 'backward'], default='forward', help='Direction when using --all-duty')
    p.add_argument('--controller', action='store_true', help='Run controller-driven mode (pygame joystick)')
    p.add_argument('--axis7', type=int, default=7, help='Index of axis to treat as axes7 (default: 7)')
    p.add_argument('--axis8', type=int, default=8, help='Index of axis to treat as axes8 (default: 8)')
    p.add_argument('--test-motor', type=int, default=None, help='Run a single-motor diagnostic (index 0..3)')
    p.add_argument('--test-duty', type=int, default=100, help='Duty for single-motor diagnostic (0-100)')
    p.add_argument('--test-dir', choices=['forward', 'reverse'], default='forward', help='Direction for single-motor diagnostic')
    p.add_argument('--invert-dir', action='store_true', help='Invert DIR polarity globally (if motor driver expects opposite DIR logic)')
    return p.parse_args()


def main():
    args = parse_args()

    # safety check
    gpio_mod.ensure_root()

    motor_pairs = default_motor_map()
    motors = [Motor(d, p) for d, p in motor_pairs]
    rd = RobotDrive(motors, invert_dir=args.invert_dir)
    rd.setup_all()

    try:
        if args.demo:
            rd.demo_sequence(duration=args.duration)
            return

        if args.controller:
            if not _HAS_PYGAME:
                print('pygame not available: install pygame to use controller mode (e.g. `pip install pygame`)')
                return
            run_with_controller(rd, axis7_idx=args.axis7, axis8_idx=args.axis8)
            return

        if args.test_motor is not None:
            idx = args.test_motor
            if not (0 <= idx < len(motors)):
                print(f'Invalid motor index {idx}; must be 0..{len(motors)-1}')
                return
            direction = True if args.test_dir == 'forward' else False
            duty = max(0, min(100, int(args.test_duty)))
            print(f'Running diagnostic on motor {idx} dir={args.test_dir} duty={duty}% for 3s')
            rd.set_motor(idx, direction, duty)
            time.sleep(3.0)
            rd.set_motor(idx, True, 0)
            return

        if args.all_duty is not None:
            direction = True if args.all_dir == 'forward' else False
            print(f"Setting all motors direction={args.all_dir} duty={args.all_duty}")
            rd.set_all(direction, args.all_duty)
            time.sleep(2.0)
            rd.stop_all()
            return

        # default: print help and exit
        print('No action specified. Use --demo or --all-duty.')
    finally:
        rd.stop_all()


# note: `main()` is called at the end of this file after helper functions


def run_with_controller(rd: RobotDrive, axis7_idx: int = 7, axis8_idx: int = 8, poll_hz: int = 30):
    """Run a controller loop using pygame joystick input.

    Mapping rules (as requested):
    - axes8 == 1 -> motor1 100% forward, motor2 100% reverse
    - axes8 == -1 -> motor1 100% reverse, motor2 100% forward
    - axes7 == 1 -> motor1 50% forward, motor2 100% reverse
    - axes7 == -1 -> motor1 100% forward, motor2 50% reverse

    Priority: if both axes provide non-zero commands, `axes8` takes priority over `axes7`.
    """
    # initialize pygame joystick
    pygame.init()
    pygame.joystick.init()
    try:
        n = pygame.joystick.get_count()
        if n == 0:
            print('No joystick detected. Connect a controller and try again.')
            return
        joy = pygame.joystick.Joystick(0)
        joy.init()
        print(f'Using joystick: {joy.get_name()} with {joy.get_numaxes()} axes')

        rd.gpio.setmode(rd.gpio.BCM)
        # ensure first two motors are set up (already done by rd.setup_all)

        clock = pygame.time.Clock()
        print('Entering controller loop. Press Ctrl-C to exit.')
        prev_cmd = None
        while True:
            for ev in pygame.event.get():
                # consume events to keep pygame responsive
                pass

            # prefer hat (D-pad) input if available; otherwise fall back to axes
            hat_val = None
            try:
                if joy.get_numhats() > 0:
                    hat_val = joy.get_hat(0)  # (x, y)
            except Exception:
                hat_val = None

            if hat_val is not None:
                # compute motor commands from hat tuple
                (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands_from_hat(hat_val)
            else:
                # read axis values and quantize to -1,0,1
                def read_axis(idx: int) -> int:
                    try:
                        v = joy.get_axis(idx)
                    except Exception:
                        return 0
                    # deadzone threshold
                    if v > 0.5:
                        return 1
                    if v < -0.5:
                        return -1
                    return 0

                a7 = read_axis(axis7_idx)
                a8 = read_axis(axis8_idx)
                # compute motor commands from axes
                (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands(a7, a8)

            # log only on change to avoid flooding
            if hat_val is not None:
                cmd = ("hat", hat_val, (m1_dir, m1_duty), (m2_dir, m2_duty))
                if cmd != prev_cmd:
                    print(f"[CTRL] hat0: {hat_val} -> m1: dir={'F' if m1_dir else 'R'} {m1_duty}%, m2: dir={'F' if m2_dir else 'R'} {m2_duty}%")
                    prev_cmd = cmd
            else:
                cmd = ("axes", a7, a8, (m1_dir, m1_duty), (m2_dir, m2_duty))
                if cmd != prev_cmd:
                    print(f"[CTRL] axes: a7={a7} a8={a8} -> m1: dir={'F' if m1_dir else 'R'} {m1_duty}%, m2: dir={'F' if m2_dir else 'R'} {m2_duty}%")
                    prev_cmd = cmd

            # apply to motors 0 and 1 (motor1 and motor2)
            try:
                rd.set_motor(0, m1_dir, m1_duty)
                rd.set_motor(1, m2_dir, m2_duty)
            except Exception as e:
                print(f'Error setting motor outputs: {e}')

            clock.tick(poll_hz)
    except KeyboardInterrupt:
        print('Controller loop stopped by user')
    finally:
        try:
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass


def compute_motor_commands(a7: int, a8: int):
    """Compute motor1 and motor2 commands from quantized axis inputs.

    Inputs a7, a8: -1, 0, or 1 (integers)
    Returns: ((m1_dir: bool, m1_duty: int), (m2_dir: bool, m2_duty: int))
    Direction: True = forward, False = reverse
    """
    # defaults
    m1_dir = True
    m2_dir = True
    m1_duty = 0
    m2_duty = 0

    if a8 != 0:
        # axes8 has priority
        if a8 == 1:
            m1_dir = True
            m1_duty = 100
            m2_dir = False
            m2_duty = 100
        else:  # a8 == -1
            m1_dir = False
            m1_duty = 100
            m2_dir = True
            m2_duty = 100
    elif a7 != 0:
        if a7 == 1:
            m1_dir = True
            m1_duty = 50
            m2_dir = False
            m2_duty = 100
        else:  # a7 == -1
            m1_dir = True
            m1_duty = 100
            m2_dir = False
            m2_duty = 50
    else:
        # neutral: stop both
        m1_duty = 0
        m2_duty = 0

    return (m1_dir, m1_duty), (m2_dir, m2_duty)


def compute_motor_commands_from_hat(hat):
    """Compute motor commands from a hat tuple (x, y).

    Mapping (as requested):
    - (0, 1): forward  (m1 100% F, m2 100% R)
    - (0, -1): back    (m1 100% R, m2 100% F)
    - (-1, 0): left    (m1 50% F, m2 100% R)
    - (1, 0): right    (m1 100% F, m2 50% R)
    """
    try:
        x, y = hat
    except Exception:
        return (True, 0), (True, 0)

    # defaults: stop
    m1_dir = True
    m2_dir = True
    m1_duty = 0
    m2_duty = 0

    if (x, y) == (0, 1):
        m1_dir, m1_duty = True, 100
        m2_dir, m2_duty = False, 100
    elif (x, y) == (0, -1):
        m1_dir, m1_duty = False, 100
        m2_dir, m2_duty = True, 100
    elif (x, y) == (-1, 0):
        m1_dir, m1_duty = True, 50
        m2_dir, m2_duty = False, 100
    elif (x, y) == (1, 0):
        m1_dir, m1_duty = True, 100
        m2_dir, m2_duty = False, 50

    return (m1_dir, m1_duty), (m2_dir, m2_duty)


if __name__ == '__main__':
    main()
