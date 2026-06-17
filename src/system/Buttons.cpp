#include "Buttons.h"

// 0 is the auto sentinel; all other values are manual brightness levels
static constexpr uint8_t  kBrightnessSteps[]  = { 255, 128, 32, 1, 0 };
static constexpr int      kBrightnessStepCount = 5;
// pitch tracks brightness: A6 → E6 → C6 → A5, the notes of an A minor chord (root, fifth, third, root an octave down); index matches kBrightnessSteps[0-3]
static constexpr uint16_t kBrightTones[]       = { 1760, 1319, 1047, 880 };

void Buttons::begin() {
    _topHeld           = false;
    _topPressStartMs   = 0;
    _frontHeld         = false;
    _frontLongFired    = false;
    _frontPressStartMs = 0;
    _brightnessStepIdx = 0;
}

void Buttons::update(DeviceState& state, PowerManager& power) {
    // Front button (BtnA = GPIO 37): short press = cycle screens / BLE event;
    //                                long press  = step through brightness levels
    bool frontDown = M5.BtnA.isPressed();
    if (frontDown) {
        if (!_frontHeld) {
            _frontHeld         = true;
            _frontLongFired    = false;
            _frontPressStartMs = millis();
        } else if (!_frontLongFired && (millis() - _frontPressStartMs) >= LONG_PRESS_A_MS) {
            _frontLongFired = true;
            // Park at the auto slot (4) so the first press from auto lands on highest.
            if (state.autodimEnabled) _brightnessStepIdx = 4;
            _brightnessStepIdx = (_brightnessStepIdx + 1) % kBrightnessStepCount;
            uint8_t step = kBrightnessSteps[_brightnessStepIdx];
            if (step == 0) {
                state.autodimEnabled      = true;
                state.melodyNotes[0]      = {kBrightTones[0], 80};
                state.melodyNotes[1]      = {0,                60};
                state.melodyNotes[2]      = {kBrightTones[0], 80};
                state.melodyPendingLength = 3;
            } else {
                state.manualBrightnessVal = step;
                state.autodimEnabled      = false;
                state.melodyNotes[0]      = {kBrightTones[_brightnessStepIdx], 80};
                state.melodyPendingLength = 1;
            }
            state.melodyPending = true;
        }
    } else {
        if (_frontHeld) {
            bool wasShort = (millis() - _frontPressStartMs) < LONG_PRESS_A_MS;
            _frontHeld      = false;
            _frontLongFired = false;
            if (wasShort) {
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
