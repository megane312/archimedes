# MD10C + Raspberry Pi テスト手順

このドキュメントは `sample.py` を Raspberry Pi（Pi 5 等）で安全にテストするための手順をまとめています。

前提:
- `sample.py` は `DIR_PIN = 17`, `PWM_PIN = 18`（BCM）を使用します。配線は必要に応じて変更してください。
- 実機でGPIOにアクセスするには通常 root 権限が必要です（`sudo`）。

安全注意:
- 電源を入れる前に配線を必ず確認してください。
- モーターの電流が高い場合は外部電源を使用し、Pi とドライバのGNDを共通にしてください。
- モーターが空転しても周囲に危険がない状態でテストしてください。

配線（基本）:
- MD10C V+ : モータ用電源の + (Pi では供給しないでください)
- MD10C GND: モータ用電源の - と Raspberry Pi の GND を共通にする
- MD10C DIR: Raspberry Pi `GPIO17` (BCM 17)
- MD10C PWM: Raspberry Pi `GPIO18` (BCM 18)
- MD10C ENABLE（存在する場合）: 必要に応じて接続/制御

準備:
1. Pi に `sample.py` と同じディレクトリにある `run_test.sh` を転送済みであることを確認。
2. 必要な場合は `RPi.GPIO` をインストール:

```bash
sudo apt update
sudo apt install python3-rpi.gpio
# もしくは pip:
sudo pip3 install RPi.GPIO
```

実行手順（実機）:
1. 電源を切って配線を確認。
2. 電源を入れる。
3. `run_test.sh` に実行権限を付与して実行:

```bash
cd /home/archimedes/ドキュメント
chmod +x run_test.sh
sudo ./run_test.sh
```

ログは `sample_test_YYYYMMDD_HHMMSS.log` に保存され、最後の50行がターミナルに表示されます。

トラブルシュート:
- `Cannot determine SOC peripheral base address` のようなエラーが出る場合、`sudo` で実行しているか確認してください。
- `ImportError: No module named RPi.GPIO` の場合は上記インストール手順を実行してください。

結果を共有する際は生成されたログファイルの内容（特に例外トレース）を貼ってください。こちらで次の調整を案内します。

短い追記: コントローラ駆動・診断ツールについて
---------------------------------

このリポジトリにはコントローラ操作とハードウェア診断を補助するスクリプトを追加しています。簡単な使い方を以下に示します。

- コントローラ駆動モード (`robot_drive.py`):
	- ジョイスティックのハット（D-pad）を優先してモータ制御します。デフォルトで `hats[0]` の値で前進/後退/左右旋回を行います。
	- 起動方法（推奨: 非 root でまず試す）:
		```bash
		PYTHONPATH=. python3 robot_drive.py --controller
		# あるいは権限が必要な場合
		sudo PYTHONPATH=. python3 robot_drive.py --controller
		```
	- 軸インデックスを変える場合は `--axis7` / `--axis8` を指定します（既存の軸フォールバックが動作します）。
	- DIR 極性が逆の場合は `--invert-dir` を付けて反転できます。

- 診断ツール (`tools/`):
	- `tools/joy_inspect.py` : ジョイスティックの軸・ボタン・ハットのインデックスと値を時刻付きで表示します（コントローラの割当確認に便利）。
		```bash
		PYTHONPATH=. python3 tools/joy_inspect.py --duration 30
		```
	- `tools/pwm_probe.py` : 指定モータに対して時刻付きで PWM/DIR を出力するプローブ。マルチメータ/オシロで信号を観測する際に使います。
		```bash
		sudo PYTHONPATH=. python3 tools/pwm_probe.py
		```
	- `tools/dir_toggle.py` : 単純に DIR を切り替えながら PWM を出力する短い診断スクリプト。

- テスト:
	- 単体のマッピング関数に対する簡易テストを `tests/test_compute_motor_commands.py` に追加しています。ワークスペースのルートで実行できます:
		```bash
		PYTHONPATH=. python3 tests/test_compute_motor_commands.py
		```

注意: モータドライバ（MD10C 等）やモータの電源仕様を必ず確認してください。高デューティで両モータを同時に駆動すると大電流が流れるため配線や電源容量に注意が必要です。