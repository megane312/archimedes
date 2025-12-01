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