#include <Arduino.h>
#include "model/DeviceState.h"
#include "imu/ImuManager.h"
#include "ble/BleManager.h"
#include "ui/Display.h"
#include "system/Buttons.h"
#include "system/PowerManager.h"

// --- Global singletons ---
DeviceState  g_state;
ImuManager   g_imu;
BleManager   g_ble;
Display      g_display;
Buttons      g_buttons;
PowerManager g_power;

static uint32_t s_lastBatMs = 0;

static void checkMessageExpiry(DeviceState& state) {
    if (!state.messageActive) return;
    if (state.messagePersistent) return;
    if (state.messageExpiresAtMs == 0) return;
    if (millis() >= state.messageExpiresAtMs) {
        state.messageActive = false;
        state.screenIndex   = state.prevScreenIndex;
    }
}

void setup() {
    Serial.begin(115200);

    memset(&g_state, 0, sizeof(g_state));
    g_state.screenIndex     = SCREEN_CLINOMETER;
    g_state.prevScreenIndex = SCREEN_CLINOMETER;
    strcpy(g_state.raText,  "--:--:--");
    strcpy(g_state.decText, "--:--:--");
    strcpy(g_state.altText, "---");
    strcpy(g_state.azText,  "---");

    g_power.begin();
    g_buttons.begin();
    g_display.begin();
    g_imu.begin();
    g_ble.begin(&g_state);
}

void loop() {
    g_imu.update(g_state);
    g_buttons.update(g_state, g_power);
    checkMessageExpiry(g_state);

    uint32_t now = millis();
    if ((now - s_lastBatMs) >= 5000) {
        g_state.batteryVoltage = g_power.readBatteryVoltage();
        s_lastBatMs = now;
    }

    g_ble.update(g_state);
    g_display.update(g_state);
    delay(1);
}
