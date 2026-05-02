#include "ImuManager.h"
#include <MPU6886.h>
#include <math.h>

static MPU6886 s_imu;

void ImuManager::begin() {
    _lastTheta    = 0.0f;
    _lastPhi      = 0.0f;
    _lastSampleMs = 0;
    s_imu.Init();
}

void ImuManager::update(DeviceState& state) {
    uint32_t now = millis();
    if ((now - _lastSampleMs) < SAMPLE_INTERVAL_MS) return;
    _lastSampleMs = now;

    float ax, ay, az;
    s_imu.getAccelData(&ax, &ay, &az);

    float rawTheta = 0.0f, rawPhi = 0.0f;
    if (ax > -1.0f && ax < 1.0f) {
        rawTheta = asinf(-ax) * 57.295f;
    }
    rawPhi = atan2f(ay, az) * 57.295f;

    _lastTheta = ALPHA * rawTheta + (1.0f - ALPHA) * _lastTheta;
    _lastPhi   = ALPHA * rawPhi   + (1.0f - ALPHA) * _lastPhi;

    state.tiltXDeg       = _lastTheta;
    state.tiltYDeg       = _lastPhi;
    state.tiltTimestampMs = now;
}
