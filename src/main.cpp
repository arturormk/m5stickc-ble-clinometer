#include <Arduino.h>
#include <M5Unified.h>
#include "model/DeviceState.h"
#include "imu/ImuManager.h"
#include "ble/BleManager.h"
#include "ui/Display.h"
#include "system/Buttons.h"
#include "system/PowerManager.h"
#include "system/Nvm.h"
#include "system/BatLog.h"

// --- Global singletons ---
DeviceState  g_state;
ImuManager   g_imu;
BleManager   g_ble;
Display      g_display;
Buttons      g_buttons;
PowerManager g_power;
BatLog       g_batLog;

static uint32_t s_lastBatMs = 0;

static void tickMelody(DeviceState& state) {
    if (!M5.Speaker.isEnabled()) return;
    if (state.melodyPending) {
        state.melodyLength      = state.melodyPendingLength;
        state.melodyNoteIdx     = 0;
        state.melodyNoteUntilMs = 0;
        state.melodyPending     = false;
        M5.Speaker.setVolume(180);
    }
    if (state.melodyLength == 0) return;
    uint32_t now = millis();
    if (now < state.melodyNoteUntilMs) return;
    if (state.melodyNoteIdx >= state.melodyLength) {
        state.melodyLength = 0;
        return;
    }
    MelodyNote& n = state.melodyNotes[state.melodyNoteIdx++];
    state.melodyNoteUntilMs = now + n.durMs;
    if (n.freqHz == 0)
        M5.Speaker.stop();
    else
        M5.Speaker.tone((float)n.freqHz, n.durMs);
}

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
    g_state.longitudeDeg       = NAN;  // 0.0f is a valid longitude; NaN means not configured
    g_state.pendingBleHelpLine = -1;   // 0 would trigger immediate HELP output
    g_state.pendingBatLogLine  = -1;
    g_state.pendingBatLogEnd   = -1;
    g_state.screenIndex     = SCREEN_CLINOMETER;
    g_state.prevScreenIndex = SCREEN_CLINOMETER;
    g_state.batteryLevel    = -1;
    strcpy(g_state.raText,  "--:--:--");
    strcpy(g_state.decText, "--:--:--");
    strcpy(g_state.altText, "---");
    strcpy(g_state.azText,  "---");

    g_state.lastBleCommandMs = millis();

    g_power.begin();
    g_buttons.begin();
    g_batLog.begin();
    g_display.begin(&g_batLog);
    g_imu.begin();
    g_ble.begin(&g_state, &g_imu, &g_batLog);
    Nvm::load(g_state, g_imu);
    g_batLog.onEvent(BAT_LOG_BOOT, g_state);
}

void loop() {
    M5.update();
    g_imu.update(g_state);
    g_buttons.update(g_state, g_power);
    checkMessageExpiry(g_state);
    tickMelody(g_state);

    uint32_t now = millis();
    if ((now - s_lastBatMs) >= 5000) {
        g_state.batteryVoltage = g_power.readBatteryVoltage();
        g_state.batteryLevel   = g_power.readBatteryLevel();
        s_lastBatMs = now;
    }

    g_batLog.tick(g_state);
    g_ble.update(g_state);
    if (g_state.pendingReboot) {
        delay(200);   // allow BLE notification to drain before reset
        ESP.restart();
    }
    g_display.update(g_state);
    delay(1);
}
