#include "PowerManager.h"
#include <Wire.h>
#include <esp_system.h>
#include <driver/gpio.h>

#define PIN_BATTERY_VOLTAGE 38

void PowerManager::begin() {
    gpio_reset_pin((gpio_num_t)POWER_HOLD_PIN);
    pinMode(POWER_HOLD_PIN, OUTPUT);
    digitalWrite(POWER_HOLD_PIN, HIGH);
    Wire1.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    analogReadResolution(12);
    analogSetPinAttenuation(PIN_BATTERY_VOLTAGE, ADC_11db);
}

float PowerManager::readBatteryVoltage() {
    int sensorValue = analogRead(PIN_BATTERY_VOLTAGE);
    float voltage = sensorValue * 3300.0f / 4095.0f / 1000.f * 2.0f;
    return voltage;
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
