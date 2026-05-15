#pragma once
#include "../model/DeviceState.h"

class ImuManager {
public:
    void begin();
    void update(DeviceState& state);

    // Store current orientation as the pitch=0, roll=0 reference.
    // Returns the normalised reference gravity vector via the out-params so the
    // caller can persist it for later use with calibrateFrom().
    void calibrate(float& refGx, float& refGy, float& refGz);

    // Apply a previously saved reference gravity vector directly, without
    // needing the device to be in that orientation.
    void calibrateFrom(float gx, float gy, float gz);

    // Return the currently active reference gravity vector.
    void getCalibrationRef(float& gx, float& gy, float& gz) const;

    // Restore factory reference (flat = 0,0).
    void resetCalibration();

private:
    // Build and store the calibration matrix for the given reference gravity
    // vector (need not be normalised). Also stores the normalised vector.
    void _applyCalibration(float gx, float gy, float gz);

    // Filtered gravity vector (device frame, ~unit length)
    float _lastGx = 0.0f;
    float _lastGy = 0.0f;
    float _lastGz = 1.0f;

    // Stored normalised reference gravity vector (identity = (0, 0, 1))
    float _calRefGx = 0.0f;
    float _calRefGy = 0.0f;
    float _calRefGz = 1.0f;

    // 3×3 rotation matrix: maps raw gravity to calibrated frame.
    float _calMat[3][3];

    uint32_t _lastSampleMs = 0;

    static constexpr float    ALPHA              = 0.2f;
    static constexpr uint32_t SAMPLE_INTERVAL_MS = 67; // ~15 Hz
};
