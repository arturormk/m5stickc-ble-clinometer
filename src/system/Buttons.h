#pragma once
#include <M5Unified.h>
#include "../model/DeviceState.h"
#include "PowerManager.h"

class Buttons {
public:
    void begin();
    void update(DeviceState& state, PowerManager& power);

private:
    uint32_t _topPressStartMs   = 0;
    bool     _topHeld           = false;

    uint32_t _frontPressStartMs = 0;
    bool     _frontHeld         = false;
    bool     _frontLongFired    = false;
    uint8_t  _brightnessStepIdx = 0;

    static constexpr uint32_t LONG_PRESS_MS   = 2000;
    static constexpr uint32_t LONG_PRESS_A_MS = 1000;
};
