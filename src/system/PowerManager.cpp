#include "PowerManager.h"
#include <M5Unified.h>
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
    if (M5.Speaker.isEnabled()) {
        M5.Speaker.setVolume(180);
        const struct { uint16_t hz; uint16_t ms; } notes[] = {
            {784, 125}, {659, 125}, {587, 125}, {523, 125}, {392, 250}
        };
        for (auto& n : notes) {
            M5.Speaker.tone(n.hz, n.ms);
            delay(n.ms);
        }
        M5.Speaker.stop();
    }
    M5.Power.powerOff();
}
