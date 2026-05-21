#pragma once
#include "../model/DeviceState.h"
#include "../imu/ImuManager.h"

class Nvm {
public:
    static void load(DeviceState& state, ImuManager& imu);
    static bool saveAll(const DeviceState& state, ImuManager& imu);
    static void clear();
    static void restore(DeviceState& state, ImuManager& imu);
    static void formatStatus(char* buf, size_t len);

    // Rebuild the runtime time anchor from the RTC + current device config.
    // Call at boot (via load()) and after SET_TIME, SET_TIME_ZONE, SET_LONGITUDE.
    static void rebuildAnchor(DeviceState& state);

private:
    static void _applyData(DeviceState& state, ImuManager& imu);
};
