"""Toggle DIR and PWM for motor 0 to help hardware debugging.

Usage:
  sudo PYTHONPATH=. python3 tools/dir_toggle.py [--duty N] [--period S] [--cycles C]

This script will set motor 0 PWM to `duty` and toggle DIR every `period` seconds
for `cycles` times. It prints actions to stdout for measurement correlation.
"""
import time
import argparse
from robot_drive import default_motor_map, Motor, RobotDrive


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--duty', type=int, default=50)
    p.add_argument('--period', type=float, default=1.0)
    p.add_argument('--cycles', type=int, default=6)
    args = p.parse_args()

    motor_pairs = default_motor_map()
    motors = [Motor(d, p) for d, p in motor_pairs]
    rd = RobotDrive(motors)
    rd.setup_all()

    try:
        duty = max(0, min(100, args.duty))
        print(f"Starting DIR toggle: motor=0 duty={duty}% period={args.period}s cycles={args.cycles}")
        dir_state = True
        for i in range(args.cycles):
            dir_state = not dir_state
            print(f"Cycle {i+1}/{args.cycles}: setting DIR={'HIGH' if dir_state else 'LOW'} PWM={duty}%")
            rd.set_motor(0, dir_state, duty)
            time.sleep(args.period)
        print("Test complete: stopping motor 0")
        rd.set_motor(0, True, 0)
    finally:
        rd.stop_all()

if __name__ == '__main__':
    main()
