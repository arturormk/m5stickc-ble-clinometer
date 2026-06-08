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
            int from = (state.screenIndex >= SCREEN_SYSINFO_1) ? SCREEN_BATTERY : state.screenIndex;
            state.screenIndex = (from + 1) % 5;
        }
    }

    // Side button (BtnB = GPIO 39): short press = reboot (not Core2, which has a hw reset), long press = deep sleep
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
                if (state.screenIndex == SCREEN_BATTERY) {
                    state.screenIndex = SCREEN_SYSINFO_1;
                } else if (state.screenIndex >= SCREEN_SYSINFO_1 && state.screenIndex < SCREEN_SYSINFO_LAST) {
                    state.screenIndex++;
                } else if (state.screenIndex == SCREEN_SYSINFO_LAST) {
                    state.screenIndex = SCREEN_BATTERY;
                } else if (M5.getBoard() != m5::board_t::board_M5StackCore2) {
                    power.reboot();
                }
            }
        }
    }
}
