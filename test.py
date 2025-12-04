#include <wiringPi.h>

#include <stdio.h>

#define IN1 23  // GPIO 23

#define IN2 24  // GPIO 24

void setup() {
    wiringPiSetupGpio();  // GPIOモードを使用
    pinMode(IN1, OUTPUT);
    pinMode(IN2, OUTPUT);
}

void forward() {
    digitalWrite(IN1, HIGH);  // IN1をHIGHに設定
    digitalWrite(IN2, LOW);   // IN2をLOWに設定
    printf("モータが正転しています\n");
}

void backward() {
    digitalWrite(IN1, LOW);   // IN1をLOWに設定
    digitalWrite(IN2, HIGH);  // IN2をHIGHに設定
    printf("モータが逆転しています\n");
}

void stop() {
    digitalWrite(IN1, LOW);  // 両方をLOWにしてモータを停止
    digitalWrite(IN2, LOW);
    printf("モータが停止しました\n");
}

int main(void) {
    setup();

    while (1) {
        forward();  // モータを正転させる
        delay(2000);  // 2秒待機
        backward();  // モータを逆転させる
        delay(2000);  // 2秒待機
        stop();  // モータを停止させる
        delay(2000);  // 2秒待機
    }

    return 0;
}