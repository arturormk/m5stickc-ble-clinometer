#pragma once
#include <M5Unified.h>
#include "../model/DeviceState.h"
#include "PowerManager.h"

class Buttons {
public:
    void begin();
    void update(DeviceState& state, PowerManager& power);

private:
    uint32_t _topPressStartMs = 0;
    bool     _topHeld         = false;

    static constexpr uint32_t LONG_PRESS_MS = 2000;
};
