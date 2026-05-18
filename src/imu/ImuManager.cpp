#include "ImuManager.h"
#include <M5Unified.h>
#include <math.h>
#include <string.h>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static void identityMat(float m[3][3]) {
    memset(m, 0, 9 * sizeof(float));
    m[0][0] = m[1][1] = m[2][2] = 1.0f;
}

// Multiply 3×3 matrix by column vector: out = M * v
static void mulMat3Vec3(const float M[3][3], float vx, float vy, float vz,
                        float& ox, float& oy, float& oz) {
    ox = M[0][0]*vx + M[0][1]*vy + M[0][2]*vz;
    oy = M[1][0]*vx + M[1][1]*vy + M[1][2]*vz;
    oz = M[2][0]*vx + M[2][1]*vy + M[2][2]*vz;
}

// ---------------------------------------------------------------------------
// ImuManager
// ---------------------------------------------------------------------------

void ImuManager::begin() {
    _lastGx = 0.0f;
    _lastGy = 0.0f;
    _lastGz = 1.0f;
    _lastSampleMs = 0;
    _applyCalibration(0.0f, 0.0f, 1.0f); // identity: ref = (0, 0, 1)
}

void ImuManager::update(DeviceState& state) {
    if (!M5.Imu.isEnabled()) {
        state.imuAvailable = false;
        return;
    }
    state.imuAvailable = true;

    uint32_t now = millis();
    if ((now - _lastSampleMs) < SAMPLE_INTERVAL_MS) return;
    _lastSampleMs = now;

    float ax, ay, az;
    M5.Imu.getAccelData(&ax, &ay, &az);

    // Low-pass filter on the gravity vector
    _lastGx = ALPHA * ax + (1.0f - ALPHA) * _lastGx;
    _lastGy = ALPHA * ay + (1.0f - ALPHA) * _lastGy;
    _lastGz = ALPHA * az + (1.0f - ALPHA) * _lastGz;

    state.gravX  = _lastGx;
    state.gravY  = _lastGy;
    state.accMag = sqrtf(_lastGx*_lastGx + _lastGy*_lastGy + _lastGz*_lastGz);

    // Apply calibration rotation
    float gcx, gcy, gcz;
    mulMat3Vec3(_calMat, _lastGx, _lastGy, _lastGz, gcx, gcy, gcz);

    // StickC series: IMU X axis runs along the physical long axis (Y of the case),
    // so tipping the long end changes gcx → pitch = atan2(-gcx, gcz).
    // Other boards (Core2, CoreS3): IMU Y axis runs along the physical long axis,
    // so tipping the long end changes gcy → pitch = atan2(gcy, gcz).
    if (M5.getBoard() == m5::board_t::board_M5StickCPlus2
            || M5.getBoard() == m5::board_t::board_M5StickCPlus) {
        state.pitchDeg = atan2f(-gcx, gcz) * 57.2957795f;
        state.rollDeg  = atan2f( gcy, gcz) * 57.2957795f;
    } else {
        state.pitchDeg = atan2f( gcy, gcz) * 57.2957795f;
        state.rollDeg  = atan2f(-gcx, gcz) * 57.2957795f;
    }

    state.tiltTimestampMs = now;
}

void ImuManager::_applyCalibration(float gx, float gy, float gz) {
    // Normalise
    float mag = sqrtf(gx*gx + gy*gy + gz*gz);
    if (mag < 0.001f) return; // degenerate input — leave current calibration

    gx /= mag;  gy /= mag;  gz /= mag;

    // Store normalised reference for later retrieval
    _calRefGx = gx;
    _calRefGy = gy;
    _calRefGz = gz;

    // Compute R such that R * (gx, gy, gz) = (0, 0, 1) using Rodrigues' formula.
    // Rotation axis k = cross(g, (0,0,1)) = (gy, -gx, 0); sin_a = |k|; cos_a = gz
    float kx = gy, ky = -gx; // kz = 0
    float sin_a = sqrtf(kx*kx + ky*ky);
    float cos_a = gz;

    if (sin_a < 0.001f) {
        if (cos_a > 0.0f) {
            identityMat(_calMat); // already aligned with reference
        } else {
            // 180° around X: (x, y, z) → (x, -y, -z)
            identityMat(_calMat);
            _calMat[1][1] = -1.0f;
            _calMat[2][2] = -1.0f;
        }
        return;
    }

    kx /= sin_a;
    ky /= sin_a;
    // Rodrigues: R = cos_a·I + (1−cos_a)·k⊗kᵀ + sin_a·K
    // K (skew-symmetric, kz=0): K[0][2]=ky, K[1][2]=-kx, K[2][0]=-ky, K[2][1]=kx
    float t = 1.0f - cos_a;
    _calMat[0][0] = cos_a + t*kx*kx;
    _calMat[0][1] = t*kx*ky;
    _calMat[0][2] = sin_a*ky;
    _calMat[1][0] = t*ky*kx;
    _calMat[1][1] = cos_a + t*ky*ky;
    _calMat[1][2] = -sin_a*kx;
    _calMat[2][0] = -sin_a*ky;
    _calMat[2][1] =  sin_a*kx;
    _calMat[2][2] = cos_a;
}

void ImuManager::calibrate(float& refGx, float& refGy, float& refGz) {
    _applyCalibration(_lastGx, _lastGy, _lastGz);
    refGx = _calRefGx;
    refGy = _calRefGy;
    refGz = _calRefGz;
}

void ImuManager::calibrateFrom(float gx, float gy, float gz) {
    _applyCalibration(gx, gy, gz);
}

void ImuManager::getCalibrationRef(float& gx, float& gy, float& gz) const {
    gx = _calRefGx;
    gy = _calRefGy;
    gz = _calRefGz;
}

void ImuManager::resetCalibration() {
    _applyCalibration(0.0f, 0.0f, 1.0f);
}
