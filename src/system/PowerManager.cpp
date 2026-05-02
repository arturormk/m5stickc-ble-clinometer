#include "PowerManager.h"
#include <Wire.h>
#include <esp_system.h>
#include <driver/gpio.h>

void PowerManager::begin() {
    gpio_reset_pin((gpio_num_t)POWER_HOLD_PIN);
    pinMode(POWER_HOLD_PIN, OUTPUT);
    digitalWrite(POWER_HOLD_PIN, HIGH);
    Wire1.begin(I2C_SDA_PIN, I2C_SCL_PIN);
}

float PowerManager::readBatteryVoltage() {
    Wire1.beginTransmission(AXP192_ADDR);
    Wire1.write(0x78);
    Wire1.endTransmission(false);
    Wire1.requestFrom((uint8_t)AXP192_ADDR, (uint8_t)2);
    uint8_t hi = Wire1.available() ? Wire1.read() : 0;
    uint8_t lo = Wire1.available() ? Wire1.read() : 0;
    uint16_t raw = ((uint16_t)hi << 4) | (lo >> 4);
    return raw * 1.1f / 1000.0f;
}

void PowerManager::reboot() {
    esp_restart();
}

void PowerManager::deepSleep() {
    // Cut power via AXP192
    Wire1.beginTransmission(AXP192_ADDR);
    Wire1.write(0x32);
    Wire1.endTransmission(false);
    Wire1.requestFrom((uint8_t)AXP192_ADDR, (uint8_t)1);
    uint8_t val = Wire1.available() ? Wire1.read() : 0;
    val |= 0x80; // set bit 7 to power off

    Wire1.beginTransmission(AXP192_ADDR);
    Wire1.write(0x32);
    Wire1.write(val);
    Wire1.endTransmission();

    delay(500);
    // Fallback: if power-off didn't work, deep sleep indefinitely
    esp_deep_sleep_start();
}
