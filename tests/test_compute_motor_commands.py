# simple smoke tests for compute_motor_commands
from robot_drive import compute_motor_commands


def expect(a7, a8, exp_m1, exp_m2):
    (m1_dir, m1_duty), (m2_dir, m2_duty) = compute_motor_commands(a7, a8)
    print(f"input a7={a7} a8={a8} -> m1: dir={m1_dir} duty={m1_duty}, m2: dir={m2_dir} duty={m2_duty}")
    assert (m1_dir, m1_duty) == exp_m1, f"m1 mismatch: got {(m1_dir,m1_duty)} expected {exp_m1}"
    assert (m2_dir, m2_duty) == exp_m2, f"m2 mismatch: got {(m2_dir,m2_duty)} expected {exp_m2}"


if __name__ == '__main__':
    # axes8=1 -> m1 100% forward, m2 100% reverse
    expect(0, 1, (True, 100), (False, 100))
    # axes8=-1 -> m1 100% reverse, m2 100% forward
    expect(0, -1, (False, 100), (True, 100))
    # axes7=1 -> m1 50% forward, m2 100% reverse
    expect(1, 0, (True, 50), (False, 100))
    # axes7=-1 -> m1 100% forward, m2 50% reverse
    expect(-1, 0, (True, 100), (False, 50))
    # both zero -> stop
    expect(0, 0, (True, 0), (True, 0))
    # both non-zero: axes8 takes priority -> axes8=1
    expect(1, 1, (True, 100), (False, 100))
    print('All tests passed')
