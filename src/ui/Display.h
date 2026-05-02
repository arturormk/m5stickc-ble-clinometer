#pragma once
#include <M5GFX.h>
#include <lgfx/v1/panel/Panel_ST7789.hpp>
#include "../model/DeviceState.h"

class CLite_GFX : public lgfx::LGFX_Device {
    lgfx::Panel_ST7789 _panel_instance;
    lgfx::Bus_SPI      _bus_instance;
    lgfx::Light_PWM    _light_instance;
public:
    CLite_GFX();
};

class Display {
public:
    void begin();
    void update(const DeviceState& state);
    void setBrightness(uint8_t val);

private:
    CLite_GFX    _lcd;
    LGFX_Sprite* _sprite = nullptr;
    uint32_t     _lastRefreshMs = 0;

    void _drawClinometer(const DeviceState& state);
    void _drawTime(const DeviceState& state);
    void _drawRADec(const DeviceState& state);
    void _drawAltAz(const DeviceState& state);
    void _drawMessage(const DeviceState& state);
    void _drawBleIndicator(bool connected);
    void _flush();
};
