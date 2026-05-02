#pragma once
#include <Arduino.h>

#define POWER_HOLD_PIN 4
#define I2C_SDA_PIN    21
#define I2C_SCL_PIN    22
#define AXP192_ADDR    0x34

class PowerManager {
public:
    void  begin();
    float readBatteryVoltage();
    void  reboot();
    void  deepSleep();
};
