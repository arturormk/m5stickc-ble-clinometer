#pragma once
#include <Button.h>
#include "../model/DeviceState.h"
#include "PowerManager.h"

#define BTN_M5_PIN  37  // front M5 button
#define BTN_TOP_PIN 39  // top side button (reboot/sleep)
#define BTN_PWR_PIN 35  // power button (reserved)

class Buttons {
public:
    void begin();
    void update(DeviceState& state, PowerManager& power);

private:
    Button   _btnM5{BTN_M5_PIN,  20};
    Button   _btnTop{BTN_TOP_PIN, 20};
    Button   _btnPwr{BTN_PWR_PIN, 20};

    uint32_t _topPressStartMs;
    bool     _topHeld;

    static constexpr uint32_t LONG_PRESS_MS = 2000;
};
