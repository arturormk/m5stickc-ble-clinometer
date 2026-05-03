#pragma once
#include <M5StickCPlus2.h>
#include "../model/DeviceState.h"

class Display {
public:
    void begin();
    void update(const DeviceState& state);
    void setBrightness(uint8_t val);

private:
    LGFX_Sprite* _sprite = nullptr;
    uint32_t     _lastRefreshMs = 0;

    void _drawClinometer(const DeviceState& state);
    void _drawTime(const DeviceState& state);
    void _drawRADec(const DeviceState& state);
    void _drawAltAz(const DeviceState& state);
    void _drawBattery(const DeviceState& state);
    void _drawMessage(const DeviceState& state);
    void _drawBleIndicator(bool connected, bool nightMode);
    void _flush();
    uint16_t _c(uint16_t color, bool night) const;
};
