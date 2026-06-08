#pragma once
#include <M5Unified.h>
#include "../model/DeviceState.h"

class Display {
public:
    void begin();
    void update(const DeviceState& state);
    void setBrightness(uint8_t val);

private:
    static constexpr uint8_t  BRIGHTNESS_FULL  = 128;
    static constexpr uint8_t  BRIGHTNESS_DIM   = 30;
    static constexpr uint8_t  BRIGHTNESS_NIGHT = 40;
    static constexpr uint32_t DIM_TIMEOUT_MS   = 60000;
    static constexpr float    DIM_STABLE_DEG   = 5.0f;

    LGFX_Sprite* _sprite = nullptr;
    uint32_t     _lastRefreshMs = 0;
    int          _W = 0, _H = 0;   // screen dimensions, set in begin()
    float        _dispPitch   = 0.0f;  // display-smoothed configured pitch
    float        _dispRoll    = 0.0f;  // display-smoothed configured roll
    float        _dispUxPitch = 0.0f;  // display-smoothed standard UX pitch (for bubble)
    float        _dispUxRoll  = 0.0f;  // display-smoothed standard UX roll  (for bubble)
    DeviceState  _lastClinoState{};
    bool         _hasLastClinoState = false;

    // Dim state
    float    _dimPitchRef        = 0.0f;
    float    _dimRollRef         = 0.0f;
    uint32_t _lastTiltActivityMs = 0;
    uint8_t  _currentBrightness  = BRIGHTNESS_FULL;

    void _updateBrightness(const DeviceState& state);
    void _drawClinometer(const DeviceState& state);
    void _drawTime(const DeviceState& state);
    void _drawRADec(const DeviceState& state);
    void _drawAltAz(const DeviceState& state);
    void _drawBattery(const DeviceState& state);
    void _drawMessage(const DeviceState& state);
    void _drawSysInfo(const DeviceState& state, int page);
    void _drawBleIndicator(bool connected, bool nightMode);
    void _flush();
    uint16_t _c(uint16_t color, bool night) const;
};
