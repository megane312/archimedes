"""PWM/DIR probe for motor 0.

Usage:
  sudo PYTHONPATH=. python3 tools/pwm_probe.py

This will run a short sequence while printing timestamps so you can measure
DIR pin (Pi -> MD10C), PWM pin (Pi -> MD10C), and motor power lines with a
multimeter or oscilloscope.
"""
import time
from robot_drive import default_motor_map, Motor, RobotDrive


def ts():
    return time.strftime('%H:%M:%S') + f'.{int((time.time()%1)*1000):03d}'


def main():
    motor_pairs = default_motor_map()
    motors = [Motor(d, p) for d, p in motor_pairs]
    rd = RobotDrive(motors)
    rd.setup_all()

    try:
        print(ts(), 'Probe start')
        # Step 1: 0% -> 100% forward for 3s
        print(ts(), 'STEP 1: Set motor0 forward 100%')
        rd.set_motor(0, True, 100)
        time.sleep(3.0)

        # Step 2: 0% for 1s
        print(ts(), 'STEP 2: Stop motor0 (0%)')
        rd.set_motor(0, True, 0)
        time.sleep(1.0)

        # Step 3: 50% with DIR toggle every 1s for 6s
        print(ts(), 'STEP 3: 50% with DIR toggle')
        duty = 50
        for i in range(6):
            dir_state = (i % 2 == 0)
            print(ts(), f'  cycle {i+1}: DIR={"HIGH" if dir_state else "LOW"} PWM={duty}%')
            rd.set_motor(0, dir_state, duty)
            time.sleep(1.0)

        # Step 4: reverse 100% for 2s
        print(ts(), 'STEP 4: Set motor0 reverse 100%')
        rd.set_motor(0, False, 100)
        time.sleep(2.0)

        print(ts(), 'Probe end: stopping motor0')
        rd.set_motor(0, True, 0)
    finally:
        rd.stop_all()

if __name__ == '__main__':
    main()
