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
            self._pwm.ChangeDutyCycle(max(0, min(100, duty)))

    def stop(self):
        try:
            if self._pwm is not None:
                self._pwm.ChangeDutyCycle(0)
        except Exception:
            pass


class RobotDrive:
    def __init__(self, motors: List[Motor]):
        self.motors = motors
        self.gpio = gpio_mod.GPIO

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
        self.motors[idx].set_speed(self.gpio, direction, duty)

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
    return p.parse_args()


def main():
    args = parse_args()

    # safety check
    gpio_mod.ensure_root()

    motor_pairs = default_motor_map()
    motors = [Motor(d, p) for d, p in motor_pairs]
    rd = RobotDrive(motors)
    rd.setup_all()

    try:
        if args.demo:
            rd.demo_sequence(duration=args.duration)
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


if __name__ == '__main__':
    main()
