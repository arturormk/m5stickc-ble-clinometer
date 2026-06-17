#pragma once
#include <Arduino.h>

class PowerManager {
public:
    void  begin();
    float readBatteryVoltage();
    int   readBatteryLevel();
    void  reboot();
};
