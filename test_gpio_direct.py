#!/usr/bin/env python3
"""
GPIO Direct Test - MD10Cモータドライバへの直接制御テスト

このスクリプトは以下を確認します:
1. GPIO ピンの状態確認
2. DIR と PWM 信号の送出確認
3. モータドライバへの接続状態
"""

import time
import sys
import sample as gpio_mod

def test_gpio_pins():
    """GPIO ピンの設定と制御をテスト"""
    print("=" * 60)
    print("GPIO Direct Control Test for MD10C Motor Driver")
    print("=" * 60)

    # テストするモーター（0: m0, 1: m1など）
    motor_config = [
        (0, 17, 18, "Motor 0"),
        (1, 22, 23, "Motor 1"),
        (2, 24, 25, "Motor 2"),
        (3, 27, 12, "Motor 3"),
    ]

    gpio = gpio_mod.GPIO

    try:
        # GPIO 初期化
        print("\n[1] GPIO Initialization...")
        gpio.setmode(gpio.BCM)
        print("    ✓ GPIO mode set to BCM")

        # ピン設定
        print("\n[2] Setting up pins...")
        for motor_idx, dir_pin, pwm_pin, label in motor_config:
            try:
                gpio.setup(dir_pin, gpio.OUT)
                gpio.setup(pwm_pin, gpio.OUT)
                print(f"    ✓ {label}: DIR=GPIO{dir_pin}, PWM=GPIO{pwm_pin}")
            except Exception as e:
                print(f"    ✗ {label}: FAILED - {e}")

        # 各モーター順番にテスト
        for motor_idx, dir_pin, pwm_pin, label in motor_config:
            print(f"\n[3.{motor_idx}] Testing {label}...")
            print(f"    DIR=GPIO{dir_pin}, PWM=GPIO{pwm_pin}")

            try:
                # DIR を HIGH (正回転)
                print(f"    - Setting DIR=HIGH (forward)...", end="")
                gpio.output(dir_pin, gpio.HIGH)
                print(" ✓")

                # PWM を 50% で ON
                pwm = gpio.PWM(pwm_pin, 1000)  # 1kHz
                print(f"    - Starting PWM at 50% duty...", end="")
                pwm.start(50)
                print(" ✓")

                print(f"    - Running for 2 seconds...")
                time.sleep(2)

                # PWM を停止
                print(f"    - Stopping PWM...", end="")
                pwm.stop()
                print(" ✓")

                # DIR を LOW (逆回転)
                print(f"    - Setting DIR=LOW (reverse)...", end="")
                gpio.output(dir_pin, gpio.LOW)
                print(" ✓")

                # PWM を 50% で ON (逆回転テスト)
                print(f"    - Starting PWM at 50% duty (reverse)...", end="")
                pwm.start(50)
                print(" ✓")

                print(f"    - Running for 2 seconds...")
                time.sleep(2)

                # PWM を停止
                print(f"    - Stopping PWM...", end="")
                pwm.stop()
                print(" ✓")

                # DIR を停止
                print(f"    - Setting DIR=LOW (stop)...", end="")
                gpio.output(dir_pin, gpio.LOW)
                print(" ✓")

                print(f"    ✓ {label} test completed")

            except Exception as e:
                print(f"\n    ✗ {label} test FAILED: {e}")
                import traceback
                traceback.print_exc()

        print("\n" + "=" * 60)
        print("GPIO Direct Test COMPLETED")
        print("=" * 60)
        print("\n[Observations]")
        print("  - モーターが回転しましたか？")
        print("  - DIR ピンの変化（HIGH/LOW）は GPIO テスターで確認できましたか？")
        print("  - PWM 信号は PWM テスターで確認できましたか？")
        print("  - MD10C の LED インジケータは点灯しましたか？")

    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            print("\n[Cleanup] Cleaning up GPIO...")
            gpio.cleanup()
            print("    ✓ GPIO cleaned up")
        except Exception as e:
            print(f"    ✗ Cleanup failed: {e}")

    return True


if __name__ == '__main__':
    success = test_gpio_pins()
    sys.exit(0 if success else 1)
