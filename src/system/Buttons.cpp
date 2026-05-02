#include "Buttons.h"

void Buttons::begin() {
    _btnM5.begin();
    _btnTop.begin();
    _btnPwr.begin();
    _topHeld         = false;
    _topPressStartMs = 0;
}

void Buttons::update(DeviceState& state, PowerManager& power) {
    // --- M5 front button: cycle screens or send BLE button event ---
    if (_btnM5.pressed()) {
        if (state.messageActive && (state.messageAwaitButtons & BTN_MASK_M5)) {
            if (!state.pendingBleEventReady) {
                strncpy((char*)state.pendingBleEvent, "EVENT BUTTON M5",
                        sizeof(state.pendingBleEvent) - 1);
                state.pendingBleEventReady = true;
            }
        } else if (state.screenIndex != SCREEN_MESSAGE) {
            state.screenIndex = (state.screenIndex + 1) % 4;
        }
    }

    // --- Top button: short press = reboot, long press = deep sleep ---
    bool topDown = (_btnTop.read() == LOW);
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

    // --- Power button: reserved, no action in v1 ---
}
