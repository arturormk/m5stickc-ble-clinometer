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

private:
    static void _applyData(DeviceState& state, ImuManager& imu);
};
