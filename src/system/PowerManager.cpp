#include "PowerManager.h"
#include <M5StickCPlus2.h>
#include <esp_system.h>

void PowerManager::begin() {
    M5.begin();
}

float PowerManager::readBatteryVoltage() {
    return M5.Power.getBatteryVoltage() / 1000.0f;
}

int PowerManager::readBatteryLevel() {
    return M5.Power.getBatteryLevel();
}

void PowerManager::reboot() {
    esp_restart();
}

void PowerManager::deepSleep() {
    M5.Power.powerOff();
}
