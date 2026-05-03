#include "Buttons.h"

void Buttons::begin() {
    _topHeld         = false;
    _topPressStartMs = 0;
}

void Buttons::update(DeviceState& state, PowerManager& power) {
    // Front button (BtnA = GPIO 37): cycle screens or send BLE button event
    if (M5.BtnA.wasPressed()) {
        if (state.messageActive && (state.messageAwaitButtons & BTN_MASK_M5)) {
            if (!state.pendingBleEventReady) {
                strncpy((char*)state.pendingBleEvent, "EVENT BUTTON M5",
                        sizeof(state.pendingBleEvent) - 1);
                state.pendingBleEventReady = true;
            }
        } else if (state.screenIndex != SCREEN_MESSAGE) {
            state.screenIndex = (state.screenIndex + 1) % 5;
        }
    }

    // Side button (BtnB = GPIO 39): short press = reboot, long press = deep sleep
    bool topDown = M5.BtnB.isPressed();
    if (topDown) {
        if (!_topHeld) {
            _topHeld         = true;
            _topPressStartMs = millis();
        } else if ((millis() - _topPressStartMs) >= LONG_PRESS_MS) {
            power.deepSleep();
        }
    } else {
        if (_topHeld) {
            _topHeld = false;
            if ((millis() - _topPressStartMs) < LONG_PRESS_MS) {
                power.reboot();
            }
        }
    }
}
