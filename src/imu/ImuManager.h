#pragma once
#include "../model/DeviceState.h"

class ImuManager {
public:
    void begin();
    void update(DeviceState& state);

private:
    float    _lastTheta;
    float    _lastPhi;
    uint32_t _lastSampleMs;

    static constexpr float    ALPHA             = 0.2f;
    static constexpr uint32_t SAMPLE_INTERVAL_MS = 67; // ~15 Hz
};
